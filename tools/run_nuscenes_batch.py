from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
from trigger_engine.data.nuscenes_adapter import NuScenesAdapter
from trigger_engine.data.quality import TrajectoryQualityAnnotator
from trigger_engine.engine.trigger_engine import EngineResult, EngineStats
from trigger_engine.rules.events import TagEvent
from tools.export_viewer import build_viewer_payload, classify_event_group, render_review_index_from_payload_dir
from tools.offline_review import chunk_items, compact_review_events


@dataclass(frozen=True)
class OfflineArtifactPaths:
    output: Path
    payload_dir: Path
    view_output: Path
    viewer_dir: Path


def offline_artifact_paths(
    run_dir: Path,
    *,
    output: Path | None = None,
    payload_dir: Path | None = None,
    view_output: Path | None = None,
    viewer_dir: Path | None = None,
) -> OfflineArtifactPaths:
    return OfflineArtifactPaths(
        output=output or run_dir / "summary.json",
        payload_dir=payload_dir or run_dir / "payloads",
        view_output=view_output or run_dir / "review.html",
        viewer_dir=viewer_dir or run_dir / "viewers",
    )


def list_nuscenes_scenes(dataroot: Path, version: str = "v1.0-mini") -> list[str]:
    scene_path = dataroot / version / "scene.json"
    scenes = json.loads(scene_path.read_text(encoding="utf-8"))
    return [scene["name"] for scene in scenes]


def evaluate_nuscenes_scene(
    dataroot_text: str,
    scene: str,
    *,
    history_steps: int,
    future_steps: int,
    payload_dir_text: str | None = None,
    map_feature_limit: int = 500,
    map_crop_margin_m: float = 80.0,
) -> dict[str, object]:
    from tools.export_nuscenes_viewer import build_engine

    dataroot = Path(dataroot_text)
    started = time.perf_counter()
    base_bundle = NuScenesAdapter().load(dataroot, scene=scene)
    annotated = TrajectoryQualityAnnotator().annotate(base_bundle)
    result = build_engine().evaluate_offline_scene(annotated)
    events = list(result.events)
    diagnostics = list(result.diagnostics)
    stats = result.stats

    compacted_events = compact_review_events(events)
    review_events = [event for event in compacted_events if classify_event_group(event) == "primary"]
    tag_counts = Counter(event.tag_name for event in review_events)

    payload_output = None
    if payload_dir_text is not None and (review_events or compacted_events):
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
        payload_dir = Path(payload_dir_text)
        payload_output = payload_dir / f"nuscenes_{scene}.json"
        write_nuscenes_scene_payload(
            display_context,
            compacted_events,
            stats,
            payload_output,
            map_feature_limit=map_feature_limit,
            future_steps=future_steps,
            map_crop_margin_m=map_crop_margin_m,
            diagnostics=diagnostics,
        )

    return {
        "scene": scene,
        "scenario_id": base_bundle.scenario_id,
        "events": len(compacted_events),
        "review_events": len(review_events),
        "review_event_counts": dict(sorted(tag_counts.items())),
        "payload_output": str(payload_output) if payload_output is not None else None,
        "seconds": time.perf_counter() - started,
    }


def write_nuscenes_scene_payload(
    context,
    events,
    stats: EngineStats,
    output: Path,
    *,
    map_feature_limit: int = 500,
    future_steps: int = 8,
    map_crop_margin_m: float = 80.0,
    diagnostics=(),
) -> Path:
    compacted_events = compact_review_events(events)
    result = EngineResult(
        scenario_id=context.scenario_id,
        source=context.source,
        plan_id="classic_v1",
        events=tuple(compacted_events),
        stats=stats,
        diagnostics=tuple(diagnostics),
    )
    if hasattr(context, "watermark"):
        payload = build_viewer_payload(
            context,
            result,
            map_feature_limit=map_feature_limit,
            playback_future_frames=future_steps,
            map_crop_margin_m=map_crop_margin_m,
        )
    else:
        payload = {
            "scenario_id": context.scenario_id,
            "source": context.source,
            "events": [asdict(event) for event in compacted_events],
            "review_event_groups_by_tag": _review_groups_for_events(compacted_events),
            "stats": asdict(stats),
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _review_groups_for_events(events: list[TagEvent]) -> list[dict[str, object]]:
    groups = []
    by_tag = {}
    for index, event in enumerate(events):
        if classify_event_group(event) != "primary":
            continue
        group = by_tag.get(event.tag_name)
        if group is None:
            group = {"tag_name": event.tag_name, "event_indices": [], "count": 0}
            by_tag[event.tag_name] = group
            groups.append(group)
        group["event_indices"].append(index)
        group["count"] += 1
    return groups


def merge_scene_summaries(scene_summaries: list[dict], elapsed: float, batch_size: int) -> dict:
    review_counts = Counter()
    payload_outputs = []
    review_scenes = 0
    review_events = 0
    for item in sorted(scene_summaries, key=lambda value: value["scene"]):
        review_counts.update(item.get("review_event_counts", {}))
        review_events += int(item.get("review_events", 0))
        if int(item.get("review_events", 0)) > 0:
            review_scenes += 1
        if item.get("payload_output"):
            payload_outputs.append(item["payload_output"])
    return {
        "source_type": "nuscenes",
        "total_scenes": len(scene_summaries),
        "review_scenes": review_scenes,
        "review_events": review_events,
        "review_event_counts": dict(sorted(review_counts.items())),
        "batch_size": batch_size,
        "seconds": elapsed,
        "scenes_per_second": len(scene_summaries) / elapsed if elapsed else 0.0,
        "scene_summaries": sorted(scene_summaries, key=lambda value: value["scene"]),
        "payload_outputs": payload_outputs,
    }


def run_batch(
    dataroot: Path,
    *,
    scenes: list[str] | None,
    batch_size: int,
    workers: int,
    output: Path,
    payload_dir: Path | None,
    view_output: Path | None,
    viewer_dir: Path | None,
    history_steps: int,
    future_steps: int,
    map_feature_limit: int,
    map_crop_margin_m: float,
) -> dict:
    selected_scenes = scenes or list_nuscenes_scenes(dataroot)
    started = time.perf_counter()
    scene_summaries = []
    scene_batches = chunk_items(selected_scenes, batch_size)

    if workers <= 1:
        for scene_batch in scene_batches:
            for scene in scene_batch:
                scene_summaries.append(
                    evaluate_nuscenes_scene(
                        str(dataroot),
                        scene,
                        history_steps=history_steps,
                        future_steps=future_steps,
                        payload_dir_text=str(payload_dir) if payload_dir is not None else None,
                        map_feature_limit=map_feature_limit,
                        map_crop_margin_m=map_crop_margin_m,
                    )
                )
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for scene_batch in scene_batches:
                futures = [
                    executor.submit(
                        evaluate_nuscenes_scene,
                        str(dataroot),
                        scene,
                        history_steps=history_steps,
                        future_steps=future_steps,
                        payload_dir_text=str(payload_dir) if payload_dir is not None else None,
                        map_feature_limit=map_feature_limit,
                        map_crop_margin_m=map_crop_margin_m,
                    )
                    for scene in scene_batch
                ]
                for future in as_completed(futures):
                    scene_summaries.append(future.result())

    summary = merge_scene_summaries(scene_summaries, time.perf_counter() - started, batch_size)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if payload_dir is not None and view_output is not None:
        render_review_index_from_payload_dir(payload_dir, view_output, viewer_dir)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run offline TriggerEngine batch over nuScenes scenes.")
    parser.add_argument("--dataroot", default=str(Path("data") / "nuscenes-mini"))
    parser.add_argument("--scene", action="append", dest="scenes")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--run-dir", default=str(Path("outputs") / "offline" / "nuscenes-mini"))
    parser.add_argument("--output", default=None)
    parser.add_argument("--payload-dir", default=None)
    parser.add_argument("--view-output", default=None)
    parser.add_argument("--viewer-dir", default=None)
    parser.add_argument("--history-steps", type=int, default=8)
    parser.add_argument("--future-steps", type=int, default=8)
    parser.add_argument("--map-feature-limit", type=int, default=500)
    parser.add_argument("--map-crop-margin-m", type=float, default=80.0)
    args = parser.parse_args(argv)
    artifacts = offline_artifact_paths(
        Path(args.run_dir),
        output=Path(args.output) if args.output else None,
        payload_dir=Path(args.payload_dir) if args.payload_dir else None,
        view_output=Path(args.view_output) if args.view_output else None,
        viewer_dir=Path(args.viewer_dir) if args.viewer_dir else None,
    )

    summary = run_batch(
        Path(args.dataroot),
        scenes=args.scenes,
        batch_size=args.batch_size,
        workers=args.workers,
        output=artifacts.output,
        payload_dir=artifacts.payload_dir,
        view_output=artifacts.view_output,
        viewer_dir=artifacts.viewer_dir,
        history_steps=args.history_steps,
        future_steps=args.future_steps,
        map_feature_limit=args.map_feature_limit,
        map_crop_margin_m=args.map_crop_margin_m,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
