from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from trigger_engine.data.quality import TrajectoryQualityAnnotator
from trigger_engine.engine.trigger_engine import EngineResult
from trigger_engine.rules.events import TagEvent
from tools.export_viewer import (
    build_viewer_payload,
    classify_event_group,
    render_review_index_from_payload_dir,
)
from tools.offline_review import compact_review_events

from .artifacts import OfflineArtifactPaths, offline_artifact_paths
from .engine import build_default_engine


class OfflineSource(Protocol):
    source_type: str

    def list_units(self) -> list[str]:
        """Return source-specific scenario ids in run order."""

    def load_bundle(self, unit_id: str):
        """Load one source unit as a ScenarioBundle."""

    def payload_context(self, scenario_bundle, *, future_steps: int):
        """Return an AlignmentContext suitable for viewer payload rendering."""

    def payload_name(self, unit_id: str, scenario_bundle) -> str:
        """Return the payload JSON filename for one unit."""


@dataclass(frozen=True)
class OfflineRunConfig:
    run_dir: Path
    batch_size: int = 5
    workers: int = 1
    future_steps: int = 8
    map_feature_limit: int = 500
    map_crop_margin_m: float = 80.0
    write_payloads: bool = True
    include_scenario_summaries: bool = True


def run_offline_source(
    source: OfflineSource,
    *,
    config: OfflineRunConfig,
    engine=None,
    artifacts: OfflineArtifactPaths | None = None,
) -> dict[str, object]:
    if config.workers != 1:
        raise NotImplementedError("Unified offline runner currently supports workers=1")
    if config.batch_size <= 0:
        raise ValueError(f"batch_size must be > 0, got {config.batch_size}")

    paths = artifacts or offline_artifact_paths(config.run_dir)
    engine = engine or build_default_engine()
    if hasattr(source, "configure_for_run"):
        source.configure_for_run(config)
    started = time.perf_counter()
    summaries = []

    stream = (
        source.iter_bundles()
        if hasattr(source, "iter_bundles")
        else ((unit_id, None) for unit_id in source.list_units())
    )
    pending = []
    for stream_item in stream:
        unit_id, bundle, source_timings = _unpack_stream_item(stream_item)
        pending.append((unit_id, bundle, source_timings))
        if len(pending) < config.batch_size:
            continue
        for item_unit_id, item_bundle, item_source_timings in pending:
            summaries.append(
                evaluate_offline_unit(
                    source,
                    item_unit_id,
                    engine=engine,
                    config=config,
                    paths=paths,
                    bundle=item_bundle,
                    source_timings=item_source_timings,
                )
            )
        pending = []
    for item_unit_id, item_bundle, item_source_timings in pending:
        summaries.append(
            evaluate_offline_unit(
                source,
                item_unit_id,
                engine=engine,
                config=config,
                paths=paths,
                bundle=item_bundle,
                source_timings=item_source_timings,
            )
        )

    summary = merge_offline_summaries(
        source_type=source.source_type,
        unit_summaries=summaries,
        elapsed=time.perf_counter() - started,
        batch_size=config.batch_size,
        include_scenario_summaries=config.include_scenario_summaries,
    )
    paths.summary.parent.mkdir(parents=True, exist_ok=True)
    paths.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if config.write_payloads and paths.payload_dir.exists():
        render_review_index_from_payload_dir(paths.payload_dir, paths.review_html, paths.viewer_dir)
    return summary


def evaluate_offline_unit(
    source: OfflineSource,
    unit_id: str,
    *,
    engine,
    config: OfflineRunConfig,
    paths: OfflineArtifactPaths,
    bundle=None,
    source_timings: dict[str, float] | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    timings = Counter()
    timings.update(source_timings or {})
    if bundle is None:
        t0 = time.perf_counter()
        bundle = source.load_bundle(unit_id)
        timings["load_seconds"] += time.perf_counter() - t0
    annotated = TrajectoryQualityAnnotator().annotate(bundle)
    timings["quality_seconds"] += time.perf_counter() - started - timings["load_seconds"]
    t0 = time.perf_counter()
    result = engine.evaluate_offline_scene(annotated)
    timings["engine_seconds"] += time.perf_counter() - t0
    t0 = time.perf_counter()
    events = compact_review_events(result.events)
    review_events = [event for event in events if classify_event_group(event) == "primary"]
    tag_counts = Counter(event.tag_name for event in review_events)
    timings["postprocess_seconds"] += time.perf_counter() - t0

    payload_output = None
    if config.write_payloads and (events or review_events):
        t0 = time.perf_counter()
        context = source.payload_context(annotated, future_steps=config.future_steps)
        payload_output = paths.payload_dir / source.payload_name(unit_id, annotated)
        write_offline_payload(
            context,
            result,
            events,
            payload_output,
            config=config,
        )
        timings["payload_seconds"] += time.perf_counter() - t0

    return {
        "unit_id": unit_id,
        "scenario_id": bundle.scenario_id,
        "events": len(events),
        "review_events": len(review_events),
        "review_event_counts": dict(sorted(tag_counts.items())),
        "payload_output": str(payload_output) if payload_output is not None else None,
        "timings": dict(sorted(timings.items())),
        "_rule_profile": _collect_rule_profiles(result),
        "seconds": time.perf_counter() - started,
    }


def write_offline_payload(
    context,
    result: EngineResult,
    events: tuple[TagEvent, ...] | list[TagEvent],
    output: Path,
    *,
    config: OfflineRunConfig,
) -> Path:
    merged = EngineResult(
        scenario_id=result.scenario_id,
        source=result.source,
        plan_id=result.plan_id,
        events=tuple(events),
        stats=result.stats,
        diagnostics=result.diagnostics,
    )
    payload = build_viewer_payload(
        context,
        merged,
        map_feature_limit=config.map_feature_limit,
        playback_future_frames=config.future_steps,
        map_crop_margin_m=config.map_crop_margin_m,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def merge_offline_summaries(
    *,
    source_type: str,
    unit_summaries: list[dict[str, object]],
    elapsed: float,
    batch_size: int,
    include_scenario_summaries: bool = True,
) -> dict[str, object]:
    review_counts = Counter()
    review_scenarios = 0
    review_events = 0
    payload_outputs = []
    timings = Counter()
    rule_profiles = []
    for item in unit_summaries:
        review_count = int(item.get("review_events", 0))
        review_events += review_count
        if review_count > 0:
            review_scenarios += 1
        review_counts.update(item.get("review_event_counts", {}))
        timings.update(item.get("timings", {}))
        rule_profiles.extend(item.get("_rule_profile", []))
        if item.get("payload_output"):
            payload_outputs.append(item["payload_output"])

    summary = {
        "source_type": source_type,
        "total_scenarios": len(unit_summaries),
        "review_scenarios": review_scenarios,
        "review_events": review_events,
        "review_event_counts": dict(sorted(review_counts.items())),
        "batch_size": batch_size,
        "seconds": elapsed,
        "scenarios_per_second": len(unit_summaries) / elapsed if elapsed else 0.0,
        "timings": dict(sorted(timings.items())),
        "rule_profile": _merge_rule_profiles(rule_profiles),
        "payload_outputs": payload_outputs,
    }
    if include_scenario_summaries:
        summary["scenario_summaries"] = [_public_unit_summary(item) for item in unit_summaries]
    return summary


def _public_unit_summary(item: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _unpack_stream_item(stream_item):
    if len(stream_item) == 2:
        unit_id, bundle = stream_item
        return unit_id, bundle, None
    if len(stream_item) == 3:
        unit_id, bundle, timings = stream_item
        return unit_id, bundle, timings
    raise ValueError(f"stream item must have 2 or 3 fields, got {len(stream_item)}")


def _collect_rule_profiles(result: EngineResult) -> list[dict[str, object]]:
    profiles = []
    for diagnostic in result.diagnostics:
        if diagnostic.message == "rule_profile":
            profiles.append(dict(diagnostic.metadata))
    return profiles


def _merge_rule_profiles(profiles: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    numeric_keys = (
        "seconds",
        "frames_evaluated",
        "frames_skipped",
        "subjects_considered",
        "pair_scan_count",
        "pair_candidate_count",
        "events_emitted",
        "calls",
    )
    for profile in profiles:
        rule_id = str(profile["rule_id"])
        item = merged.setdefault(
            rule_id,
            {
                "rule_id": rule_id,
                "tag_name": profile.get("tag_name"),
                "rule_kind": profile.get("rule_kind"),
                "subject_type": profile.get("subject_type"),
            },
        )
        for key in numeric_keys:
            if key in profile:
                item[key] = item.get(key, 0) + profile[key]
    return sorted(
        merged.values(),
        key=lambda item: (-float(item.get("seconds", 0.0)), str(item.get("rule_id", ""))),
    )
