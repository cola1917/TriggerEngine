from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
THIRD_PARTY = PROJECT_ROOT / "third_party"
if THIRD_PARTY.exists() and str(THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(THIRD_PARTY))


def _build_engine(*, profile_rules: bool = False):
    from trigger_engine.engine.registry import RuleRegistry
    from trigger_engine.engine.trigger_engine import TriggerEngine
    from trigger_engine.operators.builtins import register_builtin_operators
    from trigger_engine.operators.registry import OperatorRegistry
    from trigger_engine.scenarios.classic import register_classic_scenario_pack

    operators = OperatorRegistry()
    register_builtin_operators(operators)
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    return TriggerEngine(operators, rules, profile_rules=profile_rules)


def should_keep_payload_event(event) -> bool:
    from tools.export_viewer import classify_event_group

    if classify_event_group(event) == "primary":
        return True
    metadata = event.metadata if hasattr(event, "metadata") else event.get("metadata", {})
    tag = event.tag_name if hasattr(event, "tag_name") else event.get("tag_name", "")
    return (
        tag == "vru_close_interaction"
        and isinstance(metadata, dict)
        and metadata.get("risk_level") == "medium"
    )


def _count_events(events: list) -> dict[str, object]:
    from tools.export_viewer import event_metadata, event_risk_level, event_tag, event_target_id

    tag_counts = Counter()
    risk_counts = Counter()
    subtype_counts = Counter()
    targets = set()
    for event in events:
        tag_counts[event_tag(event)] += 1
        risk_counts[event_risk_level(event)] += 1
        subtype = event_metadata(event).get("review_subtype")
        if subtype is not None:
            subtype_counts[str(subtype)] += 1
        target_id = event_target_id(event)
        if target_id is not None:
            targets.add(target_id)
    return {
        "event_count": len(events),
        "tag_counts": dict(sorted(tag_counts.items())),
        "risk_counts": dict(sorted(risk_counts.items())),
        "subtype_counts": dict(sorted(subtype_counts.items())),
        "unique_target_count": len(targets),
        "unique_target_ids": sorted(targets),
    }


def _collect_rule_profiles(result) -> list[dict[str, object]]:
    profiles = []
    for diagnostic in result.diagnostics:
        if diagnostic.message == "rule_profile":
            profiles.append(dict(diagnostic.metadata))
    return profiles


def _merge_rule_profiles(profiles: list[dict[str, object]]) -> list[dict[str, object]]:
    merged = {}
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


def evaluate_shard(
    path_text: str,
    payload_options: dict | None = None,
    profile_rules: bool = False,
) -> dict:
    from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
    from trigger_engine.data.adapters import WaymoScenarioAdapter
    from trigger_engine.data.readers import TFRecordScenarioReader
    from tools.export_viewer import build_viewer_payload, classify_event_group, event_explanation

    path = Path(path_text)
    reader = TFRecordScenarioReader()
    adapter = WaymoScenarioAdapter()
    aligner = ScenarioAlignment()
    engine = _build_engine(profile_rules=profile_rules)

    timings = Counter()
    review_counts = Counter()
    candidate_counts = Counter()
    review_risk_counts = Counter()
    candidate_risk_counts = Counter()
    review_subtype_counts = Counter()
    candidate_subtype_counts = Counter()
    review_refs = []
    payload_outputs = []
    payload_scenarios = 0
    multi_event_scenarios = 0
    rule_profiles = []
    scenario_count = 0
    started = time.perf_counter()

    for scenario_index, scenario in enumerate(reader.iter_scenarios(path)):
        scenario_count += 1

        t0 = time.perf_counter()
        bundle = adapter.from_proto(scenario, source=str(path))
        timings["adapter_seconds"] += time.perf_counter() - t0

        t0 = time.perf_counter()
        context = aligner.align(bundle)
        timings["alignment_seconds"] += time.perf_counter() - t0

        t0 = time.perf_counter()
        result = engine.evaluate(context)
        timings["engine_seconds"] += time.perf_counter() - t0
        if profile_rules:
            rule_profiles.extend(_collect_rule_profiles(result))

        review_events = [
            event for event in result.events
            if classify_event_group(event) == "primary"
        ]
        payload_events = [
            event for event in result.events
            if should_keep_payload_event(event)
        ]
        if not review_events and not payload_events:
            continue

        payload_scenarios += 1
        review_event_stats = _count_events(review_events)
        payload_event_stats = _count_events(payload_events)
        if review_event_stats["event_count"] > 1:
            multi_event_scenarios += 1
        tags = [event.tag_name for event in review_events]
        for tag in tags:
            review_counts[tag] += 1
        for tag, count in payload_event_stats["tag_counts"].items():
            candidate_counts[tag] += count
        for risk, count in review_event_stats["risk_counts"].items():
            review_risk_counts[risk] += count
        for risk, count in payload_event_stats["risk_counts"].items():
            candidate_risk_counts[risk] += count
        for subtype, count in review_event_stats["subtype_counts"].items():
            review_subtype_counts[subtype] += count
        for subtype, count in payload_event_stats["subtype_counts"].items():
            candidate_subtype_counts[subtype] += count
        ref = {
            "source": str(path),
            "scenario_index": scenario_index,
            "scenario_id": context.scenario_id,
            "review_tags": tags,
            "primary_event_count": review_event_stats["event_count"],
            "candidate_event_count": payload_event_stats["event_count"],
            "unique_target_count": payload_event_stats["unique_target_count"],
            "risk_counts": review_event_stats["risk_counts"],
            "candidate_risk_counts": payload_event_stats["risk_counts"],
            "subtype_counts": review_event_stats["subtype_counts"],
            "candidate_subtype_counts": payload_event_stats["subtype_counts"],
            "event_explanations": [event_explanation(event) for event in review_events],
        }
        if payload_options is not None:
            payload_dir = Path(str(payload_options["payload_dir"]))
            payload_dir.mkdir(parents=True, exist_ok=True)
            payload = build_viewer_payload(
                context,
                result,
                map_feature_limit=int(payload_options["map_feature_limit"]),
                playback_future_frames=int(payload_options["future_frames"]),
                map_crop_margin_m=float(payload_options["map_crop_margin_m"]),
            )
            payload["source_file"] = str(path)
            payload["scenario_index"] = scenario_index
            output = payload_dir / f"review_payload_{_shard_number(path):05d}_s{scenario_index:04d}.json"
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            ref["payload_path"] = str(output)
            payload_outputs.append(str(output))
        if not review_events:
            continue
        review_refs.append(ref)

    elapsed = time.perf_counter() - started
    return {
        "path": str(path),
        "file": path.name,
        "scenarios": scenario_count,
        "review_scenarios": len(review_refs),
        "review_event_counts": dict(sorted(review_counts.items())),
        "review_quality": {
            "payload_scenarios": payload_scenarios,
            "multi_event_scenarios": multi_event_scenarios,
            "candidate_event_counts": dict(sorted(candidate_counts.items())),
            "review_risk_counts": dict(sorted(review_risk_counts.items())),
            "candidate_risk_counts": dict(sorted(candidate_risk_counts.items())),
            "review_subtype_counts": dict(sorted(review_subtype_counts.items())),
            "candidate_subtype_counts": dict(sorted(candidate_subtype_counts.items())),
        },
        "seconds": elapsed,
        "timings": dict(sorted(timings.items())),
        "rule_profile": _merge_rule_profiles(rule_profiles) if profile_rules else [],
        "review_scenario_refs": review_refs,
        "payload_outputs": payload_outputs,
    }


def merge_shard_summaries(shards: list[dict], elapsed: float) -> dict:
    review_counts = Counter()
    candidate_counts = Counter()
    review_risk_counts = Counter()
    candidate_risk_counts = Counter()
    review_subtype_counts = Counter()
    candidate_subtype_counts = Counter()
    timings = Counter()
    rule_profiles = []
    files = {}
    review_refs = []
    total = 0
    payload_scenarios = 0
    multi_event_scenarios = 0

    for shard in sorted(shards, key=lambda item: item["path"]):
        total += int(shard["scenarios"])
        quality = shard.get("review_quality", {})
        payload_scenarios += int(quality.get("payload_scenarios", 0))
        multi_event_scenarios += int(quality.get("multi_event_scenarios", 0))
        files[shard["file"]] = {
            "scenarios": shard["scenarios"],
            "review_scenarios": shard["review_scenarios"],
            "payload_scenarios": quality.get("payload_scenarios", 0),
            "multi_event_scenarios": quality.get("multi_event_scenarios", 0),
            "seconds": shard["seconds"],
        }
        review_counts.update(shard.get("review_event_counts", {}))
        candidate_counts.update(quality.get("candidate_event_counts", {}))
        review_risk_counts.update(quality.get("review_risk_counts", {}))
        candidate_risk_counts.update(quality.get("candidate_risk_counts", {}))
        review_subtype_counts.update(quality.get("review_subtype_counts", {}))
        candidate_subtype_counts.update(quality.get("candidate_subtype_counts", {}))
        timings.update(shard.get("timings", {}))
        rule_profiles.extend(shard.get("rule_profile", []))
        review_refs.extend(shard.get("review_scenario_refs", []))

    review_refs.sort(key=lambda item: (item["source"], item["scenario_index"]))
    multi_event_refs = [
        ref for ref in review_refs
        if int(ref.get("primary_event_count", 0)) > 1
    ]
    return {
        "total_scenarios": total,
        "review_scenarios": len(review_refs),
        "review_event_counts": dict(sorted(review_counts.items())),
        "review_quality": {
            "payload_scenarios": payload_scenarios,
            "review_scenarios": len(review_refs),
            "multi_event_scenarios": multi_event_scenarios,
            "candidate_event_counts": dict(sorted(candidate_counts.items())),
            "review_risk_counts": dict(sorted(review_risk_counts.items())),
            "candidate_risk_counts": dict(sorted(candidate_risk_counts.items())),
            "review_subtype_counts": dict(sorted(review_subtype_counts.items())),
            "candidate_subtype_counts": dict(sorted(candidate_subtype_counts.items())),
            "top_multi_event_scenarios": sorted(
                multi_event_refs,
                key=lambda ref: (
                    -int(ref.get("primary_event_count", 0)),
                    ref["source"],
                    int(ref["scenario_index"]),
                ),
            )[:10],
        },
        "seconds": elapsed,
        "scenarios_per_second": total / elapsed if elapsed else 0.0,
        "timings": dict(sorted(timings.items())),
        "rule_profile": _merge_rule_profiles(rule_profiles),
        "files": files,
        "review_scenario_refs": review_refs,
        "payload_outputs": [
            payload
            for shard in sorted(shards, key=lambda item: item["path"])
            for payload in shard.get("payload_outputs", [])
        ],
    }


def write_review_payloads(
    summary: dict,
    payload_dir: Path,
    *,
    map_feature_limit: int,
    future_frames: int,
    map_crop_margin_m: float,
) -> list[Path]:
    from tools.export_viewer import build_context_and_result, build_viewer_payload

    payload_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for ref in summary["review_scenario_refs"]:
        source = Path(ref["source"])
        scenario_index = int(ref["scenario_index"])
        context, result = build_context_and_result(source, scenario_index, None)
        payload = build_viewer_payload(
            context,
            result,
            map_feature_limit=map_feature_limit,
            playback_future_frames=future_frames,
            map_crop_margin_m=map_crop_margin_m,
        )
        payload["source_file"] = str(source)
        payload["scenario_index"] = scenario_index
        shard = _shard_number(source)
        output = payload_dir / f"review_payload_{shard:05d}_s{scenario_index:04d}.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append(output)
    return outputs


def _shard_number(path: Path) -> int:
    for part in path.name.split("-"):
        if part.isdigit():
            return int(part)
    return 0


def run_batch(
    paths: list[Path],
    *,
    workers: int,
    output: Path,
    payload_dir: Path | None,
    view_output: Path | None,
    viewer_dir: Path | None,
    map_feature_limit: int,
    future_frames: int,
    map_crop_margin_m: float,
    profile_rules: bool = False,
) -> dict:
    started = time.perf_counter()
    shard_summaries = []
    payload_options = None
    if payload_dir is not None:
        payload_options = {
            "payload_dir": str(payload_dir),
            "map_feature_limit": map_feature_limit,
            "future_frames": future_frames,
            "map_crop_margin_m": map_crop_margin_m,
        }

    if workers <= 1:
        for path in paths:
            shard_summaries.append(evaluate_shard(str(path), payload_options, profile_rules))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(evaluate_shard, str(path), payload_options, profile_rules): path
                for path in paths
            }
            for future in as_completed(futures):
                shard_summaries.append(future.result())

    summary = merge_shard_summaries(shard_summaries, time.perf_counter() - started)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if payload_dir is not None:
        if view_output is not None:
            from tools.export_viewer import render_review_index_from_payload_dir

            render_review_index_from_payload_dir(payload_dir, view_output, viewer_dir)

    return summary


def generate_payloads_from_summary(
    summary_path: Path,
    *,
    payload_dir: Path,
    view_output: Path | None,
    viewer_dir: Path | None,
    map_feature_limit: int,
    future_frames: int,
    map_crop_margin_m: float,
) -> dict:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    outputs = write_review_payloads(
        summary,
        payload_dir,
        map_feature_limit=map_feature_limit,
        future_frames=future_frames,
        map_crop_margin_m=map_crop_margin_m,
    )
    summary["payload_outputs"] = [str(output) for output in outputs]
    if view_output is not None:
        from tools.export_viewer import render_review_index_from_payload_dir

        render_review_index_from_payload_dir(payload_dir, view_output, viewer_dir)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run TriggerEngine review batch over TFRecord shards.")
    parser.add_argument("paths", nargs="*", help="Waymo TFRecord shard paths")
    parser.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--output", default="review_batch_summary.json", help="Summary JSON output")
    parser.add_argument("--payload-dir", default=None, help="Optional directory for review payload JSON")
    parser.add_argument("--view-output", default=None, help="Optional review index HTML output")
    parser.add_argument("--viewer-dir", default=None, help="Optional per-payload viewer HTML directory")
    parser.add_argument("--map-feature-limit", type=int, default=300)
    parser.add_argument("--future-frames", type=int, default=30)
    parser.add_argument("--map-crop-margin-m", type=float, default=80.0)
    parser.add_argument("--profile-rules", action="store_true", help="Include per-rule engine profiling in the summary")
    parser.add_argument("--from-summary", default=None, help="Generate payload/view outputs from an existing summary JSON")
    args = parser.parse_args(argv)

    if args.from_summary:
        if not args.payload_dir:
            parser.error("--from-summary requires --payload-dir")
        summary = generate_payloads_from_summary(
            Path(args.from_summary),
            payload_dir=Path(args.payload_dir),
            view_output=Path(args.view_output) if args.view_output else None,
            viewer_dir=Path(args.viewer_dir) if args.viewer_dir else None,
            map_feature_limit=args.map_feature_limit,
            future_frames=args.future_frames,
            map_crop_margin_m=args.map_crop_margin_m,
        )
        Path(args.output).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not args.paths:
        parser.error("paths are required unless --from-summary is used")

    summary = run_batch(
        [Path(path) for path in args.paths],
        workers=args.workers,
        output=Path(args.output),
        payload_dir=Path(args.payload_dir) if args.payload_dir else None,
        view_output=Path(args.view_output) if args.view_output else None,
        viewer_dir=Path(args.viewer_dir) if args.viewer_dir else None,
        map_feature_limit=args.map_feature_limit,
        future_frames=args.future_frames,
        map_crop_margin_m=args.map_crop_margin_m,
        profile_rules=args.profile_rules,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
