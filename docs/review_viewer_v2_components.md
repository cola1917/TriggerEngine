# Review Viewer v2 Components

## Review Payload Builder

Location: `tools/export_viewer.py`

Expected functions:

```python
build_viewer_payload(
    context,
    result,
    playback_future_frames=30,
    map_feature_limit=500,
    map_crop_margin_m=80.0,
)
```

The builder should use:

- `context.input_frames`
- `context.future_frames[:playback_future_frames]`
- all `result.events`
- selected map features intersecting the scenario/event bounds

## Frame Export

Frames should include both input and future playback frames. Each frame keeps:

- `frame_index`
- `timestamp_seconds`
- `phase`
- `visibility`
- valid agents
- traffic lights

The payload should include `playback` metadata so the viewer can mark current
and future frames.

## Event Grouping

Expected helper:

```python
classify_event_group(event) -> str
```

Returns one of:

- `primary`
- `supporting`
- `debug`

Payload should include:

- `events`: all events
- `review_events`: primary events only
- `event_groups`: indexes into `events`, grouped by category

## Bounds

Expected helpers:

```python
compute_scenario_bounds(frames, margin_m=20.0) -> dict
compute_event_bounds(event, frames, margin_m=35.0) -> dict
map_feature_intersects_bounds(feature, bounds) -> bool
```

`scenario_bounds` should be based on agent positions, not all map features.
Map features should be cropped by expanded scenario/event bounds.

## Static Viewer

Location: `tools/export_viewer.py`

`render_viewer_html(payload)` should expose:

- event group selector
- view mode selector: `fit event`, `fit scenario`, `fit map`
- sequence timeline container
- selected event details

Frontend JavaScript should use payload `view` bounds instead of recomputing
global map-heavy bounds only.
