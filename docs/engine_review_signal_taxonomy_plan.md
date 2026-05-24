# Engine Review Signal Taxonomy Plan

## Context

The current engine emits many useful tags, but the viewer exposed a product
problem: not every emitted tag is a review-worthy scenario.

In the real sample payload:

```text
events: 444
vehicle_stopped: 102
adjacent_vehicle: 194
cut_in_lateral_approach: 65
same_path_overlap: 1
vehicle_stopped_for_3_frames: 81
cut_in_confirmed: 1
```

Only `cut_in_confirmed` is a high-value review scenario in this sample. The
stopped tags are useful signals, but they are not useful default review items.

The small viewer fix moved `vehicle_stopped_for_3_frames` out of default review.
The engine should own this distinction more explicitly.

## Problem

The current system has tags but no first-class tag intent.

As a result:

- viewer code has to hard-code `_PRIMARY_TAGS`
- intermediate tags can accidentally become review events
- repeated frame-level or sustained tags can flood review outputs
- future persistence might store too many low-value events
- downstream UI cannot reliably decide which events deserve analyst attention

## Design Direction

Introduce tag taxonomy as part of rule metadata and compiled plan output.

Each rule should declare the intent of the tag it emits:

- `review`
- `supporting`
- `debug`

Optional future levels:

- `persist`
- `metric_only`
- `training_candidate`

Initial rule YAML shape:

```yaml
rules:
  - id: cut_in_confirmed
    kind: temporal
    emit:
      tag: cut_in_confirmed
      intent: review

  - id: vehicle_stopped_for_3_frames
    kind: temporal
    emit:
      tag: vehicle_stopped_for_3_frames
      intent: debug

  - id: cut_in_lateral_approach
    kind: single_frame
    emit:
      tag: cut_in_lateral_approach
      intent: supporting
```

## Engine Responsibilities

The engine should keep emitting all tag events, but it should attach event
intent to every `TagEvent`.

Recommended `TagEvent.metadata` addition:

```python
metadata={
    "intent": "review",
    "source_tags": (...),
    ...
}
```

This avoids a large schema migration while making the behavior explicit.

The engine should also expose helper partitions in `EngineResult` or export
layer:

- all events
- review events
- supporting events
- debug events

If changing `EngineResult` is too invasive, keep the partitioning in the export
layer for now, but source it from event metadata rather than hard-coded viewer
sets.

## Viewer Responsibilities

The viewer should not define product semantics.

It should:

- show `review` events by default
- allow switching to supporting/debug/all for diagnosis
- keep all events available in payload when exported in debug-capable mode
- never infer high-value review status from tag names unless metadata is absent

Fallback behavior:

- if `metadata.intent` exists, use it
- otherwise use the temporary tag-name mapping

## Persistence Direction

Persist only high-value review events by default.

Recommended default persistence:

- scenario id
- source file
- tag name
- subject id/type
- frame index and timestamp
- supporting frame indices
- source tags
- enough metadata to replay local context

Do not persist every frame-level signal by default. Intermediate signals can be
recomputed or stored only in debug exports.

## Migration Plan

### Phase 1: Viewer Export Cleanup

Status: current small fix.

- remove `vehicle_stopped_for_3_frames` from review tag mapping
- keep all events in payload
- default `review_event_indices` includes only high-value events

### Phase 2: Rule Metadata

Add `intent` to rule `emit` configuration.

Tests:

- parser accepts `emits.intent`
- parser defaults missing intent conservatively to `debug`
- compiler carries intent into execution plan
- engine writes intent into `TagEvent.metadata`

### Phase 3: Export Uses Metadata

Change `classify_event_group(event)`:

1. prefer `event.metadata["intent"]`
2. fallback to tag mapping only for old events

Tests:

- event with `metadata.intent=review` enters `review_event_indices`
- event with `metadata.intent=debug` does not enter review
- tag-name fallback remains backward compatible

### Phase 4: Persistence Filter

When persistence is added, default writer should persist only review events.

Tests:

- writer persists review events by default
- debug mode can persist all events
- persisted event includes scenario id, source file, subject, frame, timestamp,
  and replay metadata

## Initial Intent Table

Review:

- `cut_in_confirmed`
- `cut_in_risk`
- `low_ttc_pair`
- `persistent_low_ttc_pair`
- `red_light_running`

Supporting:

- `adjacent_vehicle`
- `cut_in_lateral_approach`
- `same_path_overlap`
- `red_light_stop_line_approach`
- `red_light_stop_line_crossed`

Debug:

- `vehicle_stopped`
- `vehicle_stopped_for_3_frames`
- `vehicle_stopped_at_red`

## Acceptance

The default review payload should not be flooded by intermediate or repeated
signals. For the current real-data sample, default review should contain:

```text
review_tags: {'cut_in_confirmed': 1}
```

All raw events should remain available for debugging until persistence policy is
implemented.
