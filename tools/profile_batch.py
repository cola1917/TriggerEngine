from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
THIRD_PARTY = PROJECT_ROOT / "third_party"
if THIRD_PARTY.exists() and str(THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(THIRD_PARTY))

from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
from trigger_engine.data.adapters import WaymoScenarioAdapter
from trigger_engine.data.readers import TFRecordScenarioReader
from trigger_engine.engine.registry import RuleRegistry
from trigger_engine.engine.trigger_engine import TriggerEngine
from trigger_engine.operators.builtins import register_builtin_operators
from trigger_engine.operators.registry import OperatorRegistry
from trigger_engine.scenarios.classic import register_classic_scenario_pack
from tools.export_viewer import classify_event_group


def build_engine() -> TriggerEngine:
    operators = OperatorRegistry()
    register_builtin_operators(operators)
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    return TriggerEngine(operators, rules)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Profile TriggerEngine batch evaluation.")
    parser.add_argument("paths", nargs="+", help="Waymo TFRecord shard paths")
    parser.add_argument("--max-scenarios", type=int, default=None, help="Stop after this many scenarios total")
    parser.add_argument("--output", default=None, help="Optional JSON summary output")
    args = parser.parse_args(argv)

    reader = TFRecordScenarioReader()
    adapter = WaymoScenarioAdapter()
    aligner = ScenarioAlignment()
    engine = build_engine()

    counts = Counter()
    timings = Counter()
    review_counts = Counter()
    review_scenarios = []
    total = 0
    started = time.perf_counter()

    for raw_path in args.paths:
        path = Path(raw_path)
        shard_count = 0
        shard_reviews = 0
        shard_started = time.perf_counter()
        for scenario_index, scenario in enumerate(reader.iter_scenarios(path)):
            if args.max_scenarios is not None and total >= args.max_scenarios:
                break

            total += 1
            shard_count += 1

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
                if classify_event_group(event) == "primary"
            ]
            if review_events:
                shard_reviews += 1
                review_scenarios.append(
                    {
                        "source": str(path),
                        "scenario_index": scenario_index,
                        "scenario_id": context.scenario_id,
                        "review_tags": [event.tag_name for event in review_events],
                    }
                )
                for event in review_events:
                    review_counts[event.tag_name] += 1

        elapsed = time.perf_counter() - shard_started
        counts[path.name] = {
            "scenarios": shard_count,
            "review_scenarios": shard_reviews,
            "seconds": elapsed,
        }
        print(
            f"{path.name}: scenarios={shard_count} "
            f"review_scenarios={shard_reviews} seconds={elapsed:.3f}",
            flush=True,
        )
        if args.max_scenarios is not None and total >= args.max_scenarios:
            break

    elapsed = time.perf_counter() - started
    summary = {
        "total_scenarios": total,
        "review_scenarios": len(review_scenarios),
        "review_event_counts": dict(sorted(review_counts.items())),
        "seconds": elapsed,
        "scenarios_per_second": total / elapsed if elapsed else 0.0,
        "timings": dict(sorted(timings.items())),
        "files": counts,
        "review_scenario_refs": review_scenarios,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.output is not None:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
