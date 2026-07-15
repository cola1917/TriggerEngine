# Unified Offline Pipeline Plan

## Direction

Offline mining should have one source-agnostic pipeline. `source_type` selects
the adapter/source loader; it should not select a separate mining/export
pipeline.

```text
source -> OfflineSource -> ScenarioBundle
       -> TrajectoryQualityAnnotator
       -> TriggerEngine.evaluate_offline_scene
       -> unified review payload
       -> unified review html/index
```

## Source Boundary

Each source implements the same small contract:

- `list_units()`: source-specific scenario units in run order
- `load_bundle(unit_id)`: one unit to `ScenarioBundle`
- `payload_context(bundle)`: viewer playback context
- `payload_name(unit_id, bundle)`: payload JSON filename

Current implementations:

- `NuScenesOfflineSource`: unit is a nuScenes scene name/token.
- `WaymoOfflineSource`: unit is a TFRecord scenario address `path#index`.

## Export Boundary

Export is payload-driven, not source-driven. The viewer renders what exists:

- frames/agents when present
- map features when present
- traffic lights when present
- review groups when present

Missing source capabilities should be represented in adapter metadata and by
empty payload sections, not by branching the viewer by source.

## Current Entry Point

`tools/run_offline.py` is the unified CLI:

```bash
python tools/run_offline.py --source nuscenes --dataroot data/nuscenes-mini --run-dir outputs/offline/nuscenes-mini
python tools/run_offline.py --source waymo --run-dir outputs/offline/waymo data/waymo/shard.tfrecord
```

Older source-specific tools are compatibility/debug entry points during the
transition.
