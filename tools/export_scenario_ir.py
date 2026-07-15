from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trigger_engine.contracts import ScenarioIRExportConfig, build_scenario_ir
from trigger_engine.data.nuscenes_adapter import NuScenesAdapter
from trigger_engine.data.quality import TrajectoryQualityAnnotator
from trigger_engine.offline.engine import build_default_engine


def export_nuscenes_scenario_ir(
    dataroot: Path,
    *,
    scene: str,
    output: Path,
    scenario_type: str = "mined_high_value",
) -> dict[str, object]:
    bundle = NuScenesAdapter().load(dataroot, scene=scene)
    annotated = TrajectoryQualityAnnotator().annotate(bundle)
    result = build_default_engine().evaluate_offline_scene(annotated)
    review_events = tuple(event for event in result.events if event.metadata.get("intent") == "review")
    trigger_event = review_events[0] if review_events else (result.events[0] if result.events else None)
    scenario_ir = build_scenario_ir(
        annotated,
        trigger_event=trigger_event,
        events=review_events or result.events,
        config=ScenarioIRExportConfig(scenario_type=scenario_type),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scenario_ir, ensure_ascii=False, indent=2), encoding="utf-8")
    return scenario_ir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export Project 1 Scenario IR from nuScenes.")
    parser.add_argument("--dataroot", default=str(Path("data") / "nuscenes-mini"))
    parser.add_argument("--scene", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scenario-type", default="mined_high_value")
    args = parser.parse_args(argv)

    scenario_ir = export_nuscenes_scenario_ir(
        Path(args.dataroot),
        scene=args.scene,
        output=Path(args.output),
        scenario_type=args.scenario_type,
    )
    print(json.dumps({
        "scenario_id": scenario_ir["scenario_id"],
        "scenario_type": scenario_ir["scenario_type"],
        "actors": len(scenario_ir["actors"]),
        "trigger": scenario_ir["events"]["trigger"],
        "output": args.output,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
