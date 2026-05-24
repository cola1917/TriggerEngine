# Review Viewer v2 Architecture

Review Viewer v2 turns the current "openable payload" into a useful rule review
workflow. The frontend still does not run data. It only reads a stable review
payload.

## Problems In v1

- Payload only includes `input_frames`; future playback is unavailable.
- Event list is flat, so primary review targets are buried by supporting tags.
- Map features are truncated by `feature_id`, not cropped by visible area.
- Viewer fits the entire map payload, making agents and selected pairs too small.
- Temporal sequence support is only visible as raw JSON metadata.

## Target Flow

```text
offline runner -> review_payload.json -> static viewer -> human review
```

The viewer defaults to reviewing primary events, then exposes supporting/debug
events when needed.

## Payload Shape

```json
{
  "scenario_id": "...",
  "source": "...",
  "frames": [],
  "playback": {
    "history_frame_count": 11,
    "future_frame_count": 30,
    "current_frame_index": 10
  },
  "events": [],
  "review_events": [],
  "event_groups": {
    "primary": [],
    "supporting": [],
    "debug": []
  },
  "map_features": [],
  "view": {
    "scenario_bounds": {},
    "event_bounds_by_event_index": {}
  }
}
```

## Event Groups

Primary events are the review queue:

- `cut_in_confirmed`
- `cut_in_risk`
- `low_ttc_pair`
- `persistent_low_ttc_pair`
- `red_light_running`
- `vehicle_stopped_for_3_frames`

Supporting events explain sequence steps:

- `adjacent_vehicle`
- `cut_in_lateral_approach`
- `same_path_overlap`
- `red_light_stop_line_approach`
- `red_light_stop_line_crossed`

Debug events are high-volume intermediate tags:

- `vehicle_stopped`
- `vehicle_stopped_at_red`
- raw one-frame tags not listed above

## Viewer Behavior

- Default event list shows `review_events`.
- User can switch between `primary`, `supporting`, `debug`, and `all`.
- Selecting an event switches to `fit event` view.
- `fit event` bounds center on the selected subject across supporting frames and
  a small future window.
- `fit scenario` remains available as a fallback.
- Temporal sequence events show a compact timeline of source tags and supporting
  frames.

## Non-Goals

- No live backend service.
- No rule execution in frontend.
- No annotation persistence yet.
- No React/Vite app in this phase.
