# Scenario IR Contract

Scenario IR is the source-of-truth handoff from TriggerEngine to the downstream simulation projects.

It is intentionally simulator-agnostic. TriggerEngine should not export CARLA scripts, NuRec job files, OpenSCENARIO, or OpenUSD directly as its primary output. Those are adapter outputs owned by NeuralSceneBridge and ClosedLoopBench.

## Project Boundary

TriggerEngine owns:

- mining high-value events from nuScenes / future datasets
- selecting event and reconstruction windows
- exporting ego and actor reference trajectories
- exporting trigger metadata and risk metrics
- exporting map and sensor capability context

NeuralSceneBridge owns:

- `Scenario IR -> NuRec job`
- dynamic mask generation
- NuRec / Cosmos configs
- reconstruction package metrics

ClosedLoopBench owns:

- `Scenario IR -> CARLA ScenarioRunner scenario`
- ego policy execution
- replay / scripted / reactive actor policies
- closed-loop metrics and reports

## MVP Contract

The frozen cross-project IR is `scenario_ir.v1`. Legacy
`scenario_ir.mvp.v0` artifacts are not accepted as v1 because they used a
different coordinate-frame shape and yaw semantics.

Required top-level fields:

- `scenario_id`
- `scenario_type`
- `source`
- `coordinate_frame`
- `windows`
- `ego`
- `actors`
- `map_context`
- `sensors`
- `events`
- `data_requirements`
- `risk_metrics`
- `dataset_refs`
- `evaluation`
- `variants`

### Windows

MVP exports three windows:

- `event`: the closed-loop evaluation segment around the trigger
- `warmup`: short initialization window before the event
- `reconstruction`: wider segment used by NeuralSceneBridge for NuRec / Cosmos

This avoids forcing reconstruction to train only on the trigger interval.

### Coordinate Frame

nuScenes Scenario IR uses one structured `scene_local_ego_start` frame:

- right-handed coordinates;
- origin at the first scene Ego pose;
- local X points along the first Ego heading and local Y points left;
- positions are metres, timestamps are seconds, and yaw is degrees;
- `origin_global_translation`, `origin_global_rotation_wxyz`, and
  `origin_global_yaw_deg` preserve the inverse mapping to nuScenes global space.

TriggerEngine keeps its mining bundle in translation-local/global-axis form so
rule behavior does not change. The Scenario IR exporter applies the same
`R(-origin_yaw)` rotation to positions, velocity vectors, and map features, and
exports actor/Ego headings relative to the origin yaw in degrees.

### Actors

Actors include:

- `role = trigger` for the main actor when a trigger actor is known
- `role = context` for surrounding vehicles / pedestrians
- reference trajectories from nuScenes
- policy hints for MVP replay and final reactive closed-loop

nuScenes tracks are reference behavior, not counterfactual truth.

### Data Requirements

`data_requirements` makes the downstream handoff explicit.

`data_requirements.reconstruction.required` currently includes:

- `camera_images`
- `camera_calibration`
- `ego_pose`
- `actor_tracks`

NeuralSceneBridge uses these requirements to decide whether a Scenario IR has enough source material for NuRec / Cosmos reconstruction packaging.

`data_requirements.closed_loop.required` currently includes:

- `ego_initial_state`
- `actor_initial_states`
- `map_context`

ClosedLoopBench uses these requirements to decide whether a Scenario IR has enough initialization context for CARLA replay, scripted actors, and later reactive actor policies.

### Risk Metrics

`risk_metrics` is a compact summary for cross-project ranking and smoke checks. MVP+ includes:

- `trigger_time_sec`
- `trigger_tag`
- `actor_count`
- `ego_reference_state_count`

These are intentionally lightweight. Rich metrics such as min TTC, gap size, braking severity, route progress, and comfort remain final-contract additions once consumers agree on definitions.

### Dataset References

`dataset_refs` carries source lookup context for consumers without inlining dataset-specific records into the IR.

For nuScenes, the exported `scenario_id` and `source.scene_id` use the native
scene token as the canonical cross-project identifier. `source.scene_name`
retains the human-readable name for display and lookup, while
`source.scene_token` repeats the canonical token explicitly.

MVP+ includes:

- `dataset_refs.source.dataset`
- `dataset_refs.source.root`
- `dataset_refs.source.scene_id`
- `dataset_refs.source.scene_name`
- `dataset_refs.source.scene_token`
- `dataset_refs.sample_refs.status = deferred`
- `dataset_refs.index_refs.status = deferred`

The deferred sample and index refs are placeholders for future nuScenes sample tokens, frame indices, image paths, and calibration record pointers. NeuralSceneBridge should resolve them from the source dataset during reconstruction packaging; ClosedLoopBench should rely on the exported ego, actor, and map payloads until richer refs are promoted into the contract.

## Final Closed-Loop Contract

The final contract should add:

- explicit task family, such as `cut_in`, `unprotected_left_turn`, or `occluded_pedestrian_crossing`
- scenario-family parameter ranges
- conflict-point definitions
- actor behavior templates
- route/lane graph semantics beyond raw map features
- sensor rig and camera calibration records
- dataset image/sample pointers for NuRec
- risk metrics such as min TTC, gap, braking severity, and route progress
- expected ClosedLoopBench actor policy class
- links to NeuralSceneBridge reconstruction packages

## Current Bootstrap

The first real mini export is:

```text
outputs/scenario_ir/scene-1077.v1.json
```

The exporter CLI is:

```bash
python tools/export_scenario_ir.py --scene scene-1077 --output outputs/scenario_ir/scene-1077.v1.json
```
