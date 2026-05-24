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


def _build_engine():
    from trigger_engine.engine.registry import RuleRegistry
    from trigger_engine.engine.trigger_engine import TriggerEngine
    from trigger_engine.operators.builtins import register_builtin_operators
    from trigger_engine.operators.registry import OperatorRegistry
    from trigger_engine.scenarios.classic import register_classic_scenario_pack

    operators = OperatorRegistry()
    register_builtin_operators(operators)
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    return TriggerEngine(operators, rules)


def evaluate_shard(path_text: str) -> dict:
    from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
    from trigger_engine.data.adapters import WaymoScenarioAdapter
    from trigger_engine.data.readers import TFRecordScenarioReader

    path = Path(path_text)
    reader = TFRecordScenarioReader()
    adapter = WaymoScenarioAdapter()
    aligner = ScenarioAlignment()
    engine = _build_engine()

    timings = Counter()
    review_counts = Counter()
    review_refs = []
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

        review_events = [
            event for event in result.events
            if event.metadata.get("intent") == "review"
        ]
        if not review_events:
            continue

        tags = [event.tag_name for event in review_events]
        for tag in tags:
            review_counts[tag] += 1
        review_refs.append(
            {
                "source": str(path),
                "scenario_index": scenario_index,
                "scenario_id": context.scenario_id,
                "review_tags": tags,
            }
        )

    elapsed = time.perf_counter() - started
    return {
        "path": str(path),
        "file": path.name,
        "scenarios": scenario_count,
        "review_scenarios": len(review_refs),
        "review_event_counts": dict(sorted(review_counts.items())),
        "seconds": elapsed,
        "timings": dict(sorted(timings.items())),
        "review_scenario_refs": review_refs,
    }


def merge_shard_summaries(shards: list[dict], elapsed: float) -> dict:
    review_counts = Counter()
    timings = Counter()
    files = {}
    review_refs = []
    total = 0

    for shard in sorted(shards, key=lambda item: item["path"]):
        total += int(shard["scenarios"])
        files[shard["file"]] = {
            "scenarios": shard["scenarios"],
            "review_scenarios": shard["review_scenarios"],
            "seconds": shard["seconds"],
        }
        review_counts.update(shard.get("review_event_counts", {}))
        timings.update(shard.get("timings", {}))
        review_refs.extend(shard.get("review_scenario_refs", []))

    review_refs.sort(key=lambda item: (item["source"], item["scenario_index"]))
    return {
        "total_scenarios": total,
        "review_scenarios": len(review_refs),
        "review_event_counts": dict(sorted(review_counts.items())),
        "seconds": elapsed,
        "scenarios_per_second": total / elapsed if elapsed else 0.0,
        "timings": dict(sorted(timings.items())),
        "files": files,
        "review_scenario_refs": review_refs,
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
) -> dict:
    started = time.perf_counter()
    shard_summaries = []

    if workers <= 1:
        for path in paths:
            shard_summaries.append(evaluate_shard(str(path)))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(evaluate_shard, str(path)): path
                for path in paths
            }
            for future in as_completed(futures):
                shard_summaries.append(future.result())

    summary = merge_shard_summaries(shard_summaries, time.perf_counter() - started)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if payload_dir is not None:
        write_review_payloads(
            summary,
            payload_dir,
            map_feature_limit=map_feature_limit,
            future_frames=future_frames,
            map_crop_margin_m=map_crop_margin_m,
        )
        if view_output is not None:
            from tools.export_viewer import render_review_index_from_payload_dir

            render_review_index_from_payload_dir(payload_dir, view_output, viewer_dir)

    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run TriggerEngine review batch over TFRecord shards.")
    parser.add_argument("paths", nargs="+", help="Waymo TFRecord shard paths")
    parser.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--output", default="review_batch_summary.json", help="Summary JSON output")
    parser.add_argument("--payload-dir", default=None, help="Optional directory for review payload JSON")
    parser.add_argument("--view-output", default=None, help="Optional review index HTML output")
    parser.add_argument("--viewer-dir", default=None, help="Optional per-payload viewer HTML directory")
    parser.add_argument("--map-feature-limit", type=int, default=300)
    parser.add_argument("--future-frames", type=int, default=30)
    parser.add_argument("--map-crop-margin-m", type=float, default=80.0)
    args = parser.parse_args(argv)

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
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
