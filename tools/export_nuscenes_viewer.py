from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
from trigger_engine.data.nuscenes_adapter import NuScenesAdapter
from trigger_engine.data.quality import TrajectoryQualityAnnotator
from trigger_engine.engine.registry import RuleRegistry
from trigger_engine.engine.trigger_engine import EngineResult, EngineStats, TriggerEngine
from trigger_engine.operators.builtins import register_builtin_operators
from trigger_engine.operators.registry import OperatorRegistry
from trigger_engine.scenarios.classic import register_classic_scenario_pack
from tools.export_viewer import build_viewer_payload, render_viewer_html
from tools.offline_review import compact_review_events


def build_engine() -> TriggerEngine:
    operators = OperatorRegistry()
    register_builtin_operators(operators)
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    return TriggerEngine(operators, rules)


def export_nuscenes_scene_viewer(
    dataroot: Path,
    scene: str,
    output: Path,
    payload_output: Path | None = None,
    history_steps: int = 8,
    future_steps: int = 8,
    map_crop_margin_m: float = 80.0,
) -> Path:
    base_bundle = NuScenesAdapter().load(dataroot, scene=scene)
    annotated = TrajectoryQualityAnnotator().annotate(base_bundle)
    result = build_engine().evaluate_offline_scene(annotated)
    events = list(result.events)
    diagnostics = list(result.diagnostics)
    stats = result.stats

    display_bundle = NuScenesAdapter().load(
        dataroot,
        scene=scene,
        current_time_index=len(base_bundle.frames) - 1,
    )
    display_bundle = TrajectoryQualityAnnotator().annotate(display_bundle)
    display_context = ScenarioAlignment().align(
        display_bundle,
        history_steps=len(display_bundle.frames) - 1,
        future_steps=future_steps,
    )
    compacted_events = compact_review_events(events)
    merged = EngineResult(
        scenario_id=display_bundle.scenario_id,
        source=str(dataroot),
        plan_id="classic_v1",
        events=tuple(compacted_events),
        stats=stats,
        diagnostics=tuple(diagnostics),
    )
    payload = build_viewer_payload(
        display_context,
        merged,
        playback_future_frames=future_steps,
        map_crop_margin_m=map_crop_margin_m,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_viewer_html(payload), encoding="utf-8")
    if payload_output is not None:
        payload_output.parent.mkdir(parents=True, exist_ok=True)
        payload_output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export a static nuScenes TriggerEngine viewer.")
    parser.add_argument("--dataroot", default=str(Path("data") / "nuscenes-mini"))
    parser.add_argument("--scene", default="scene-0061")
    parser.add_argument("-o", "--output", default=str(Path("outputs") / "nuscenes_scene_0061.html"))
    parser.add_argument("--payload-output", default=str(Path("outputs") / "nuscenes_scene_0061_payload.json"))
    parser.add_argument("--history-steps", type=int, default=8)
    parser.add_argument("--future-steps", type=int, default=8)
    parser.add_argument("--map-crop-margin-m", type=float, default=80.0)
    args = parser.parse_args(argv)

    output = export_nuscenes_scene_viewer(
        Path(args.dataroot),
        args.scene,
        Path(args.output),
        payload_output=Path(args.payload_output) if args.payload_output else None,
        history_steps=args.history_steps,
        future_steps=args.future_steps,
        map_crop_margin_m=args.map_crop_margin_m,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
