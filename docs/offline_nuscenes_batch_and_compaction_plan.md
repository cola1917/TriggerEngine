# Offline nuScenes Batch and Review Compaction Plan

## Scope

This phase stays offline-only. It does not introduce online streaming, service
APIs, or stream/batch unification. The goal is to make the current offline
workflow reliable enough to inspect data-source adapters, rule output, and
review payload quality.

## Design

Offline processing has three layers:

1. Adapter layer converts each data source into `ScenarioBundle`.
2. Engine evaluates one scenario with an explicit evaluation mode.
3. Batch runner groups scenarios, merges summaries, and optionally writes
   payload/index artifacts.

Two evaluation modes are supported:

- `causal_watermark`: evaluate one decision point. Rules see
  `observed_frames + current_frame`; future frames are not rule input.
- `offline_full_scene`: evaluate the full scene as an offline labeling task.
  Every frame is rule input, temporal/state-machine rules run over the full
  timeline, and event policy runs once over the complete event set.

nuScenes offline batch uses `offline_full_scene`. The old runner-level
current-frame sweep is intentionally avoided because it fragments event policy
across many `evaluate()` calls.

Event policy order is:

1. compact supporting/debug intervals
2. merge review episodes over the full event timeline
3. apply cooldown to episode-level review outputs
4. apply review-family dominance

When a review rule declares both `episode` and `cooldown_frames`, the cooldown
window is also used as the sparse-hit gap for that episode. This lets offline
review outputs represent one braking episode even when the raw frame hits are
not strictly consecutive.

Offline artifacts are written under a single run directory by default:

```text
outputs/offline/nuscenes-mini/
  summary.json
  payloads/
    nuscenes_scene-1077.json
  review.html
  viewers/
    nuscenes_scene-1077.html
```

`payloads/` is the machine-readable review contract. `review.html` and
`viewers/` are derived offline inspection artifacts. CLI overrides are still
allowed for ad hoc debugging, but the default batch path should stay under the
run directory.

nuScenes batch uses scenes as the unit of work. The runner chunks scene names in
fixed-size batches:

```text
scene-1..scene-5
scene-6..scene-10
last chunk may contain fewer than 5 scenes
```

The default batch size is 5 because nuScenes mini scenes are small enough that
this gives predictable progress without making each process too coarse.

## Review Compaction

Exact dedupe is not enough for review usability. Some SDC-centric events, such
as `sdc_hard_braking`, can emit one event per nearby target for the same ego
brake frame. Those events are technically distinct by `subject_id`, but they
represent one review episode.

Offline payload compaction applies after rule evaluation and before payload
generation:

- keep exact duplicate suppression
- compact `sdc_hard_braking` by scenario/source/tag/frame/ego id
- compact repeated `sdc_hard_braking` frames by ego into an offline review
  episode when adjacent review hits are within the hard-brake cooldown window
- preserve suppressed target details in metadata
- keep target-specific events such as `vru_close_interaction`

## Acceptance

- nuScenes scenes can be chunked by `--batch-size 5`.
- nuScenes batch summary reports scenes, review counts, and payload outputs.
- `sdc_hard_braking` multi-target events compact to one review event per ego
  brake frame while preserving suppressed targets in metadata.
- repeated `sdc_hard_braking` frames such as `scene-1077` compact to one review
  episode while preserving raw frame indices in metadata.
- Existing Waymo batch behavior remains unchanged.
