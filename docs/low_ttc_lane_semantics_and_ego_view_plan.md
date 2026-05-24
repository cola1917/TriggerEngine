# Low TTC Lane Semantics And Ego-Centric Viewer Plan

## Goal

Fix two review blockers:

1. Pair-event visualization should make SDC/EGO and TARGET obvious.
2. `persistent_low_ttc_pair` should represent a plausible same-lane or same-path
   SDC risk, not a loose adjacent-lane proximity event.

This task should not change payload export shape or directory index behavior.

## Problem

Current viewer pair framing uses the average center of the pair and may use the
target heading as the local frame heading. That makes the review image unstable:

- EGO is not visually anchored.
- TARGET can be hard to distinguish.
- Front/back/side relationships drift between frames.

Current low TTC rules are SDC-centric but not lane-aware:

```text
sdc_pair + vehicle types + ego speed + target in front + low_ttc
```

The gate uses geometry:

- `pair_in_front.max_lateral_m: 4.0`
- `predicate.low_ttc.max_lateral_m: 4.0`

This can include adjacent-lane vehicles, especially on wide or curved roads.

## Viewer Design

### Ego-Centric Pair View

For `agent_pair` events:

- Parse `subject_id` as `ego_id:target_id`.
- Use the first id as EGO and second id as TARGET.
- Center the canvas local frame on EGO.
- Rotate the local frame by EGO heading.
- Place EGO in a stable lower-center anchor, not exactly in the geometric
  center, so the area in front of EGO has more screen space.
- Draw TARGET with strong contrast and role label.
- Keep non-selected agents subdued.

Expected transform:

```text
eventFrameTransform(event):
  if event.subject_type == agent_pair:
    ego = current_frame.agent(subject_id[0])
    return {
      cx: ego.x,
      cy: ego.y,
      heading: ego.heading,
      radius: 45,
      anchor: { x: 0.5, y: 0.68 }
    }
```

Projection should use the anchor:

```text
screen_x = anchor_x * canvas_width + local_x * scale
screen_y = anchor_y * canvas_height - local_y * scale
```

This makes "in front of ego" consistently point upward in the viewer.

### Required Visual Cues

- EGO fill/stroke must be visually distinct from TARGET.
- EGO label and TARGET label must be visible near the selected agents.
- Pair line remains useful but should not be the only role cue.
- Summary panel keeps EGO and TARGET ids.

## Low TTC Semantics Design

### New Operator

Add builtin pair operator:

```text
predicate.same_lane_or_path
```

Subject type:

```text
agent_pair
```

Arguments:

```yaml
max_lane_lateral_m: 1.8
max_heading_delta_rad: 0.7
fallback_max_lateral_m: 1.2
fallback_max_heading_delta_rad: 0.35
allow_fallback_without_map: true
```

Behavior:

1. Try to lane-match EGO and TARGET with `match_agent_to_lane`.
2. If both match lanes:
   - return true only when `ego_lane_id == target_lane_id`.
   - metadata should include lane ids and `mode: "lane"`.
3. If either cannot match and fallback is allowed:
   - return true only when pair is very close to the same path by strict
     ego-frame geometry:
     - absolute lateral distance <= `fallback_max_lateral_m`
     - heading delta <= `fallback_max_heading_delta_rad`
   - metadata should include `mode: "fallback_path"`.
4. If map exists and agents match different lane ids, do not fallback to loose
   geometry. Return false with metadata showing lane ids.

### Classic Rule Update

Update `low_ttc_pair`:

```yaml
- operator: predicate.same_lane_or_path
  args:
    max_lane_lateral_m: 1.8
    max_heading_delta_rad: 0.7
    fallback_max_lateral_m: 1.2
    fallback_max_heading_delta_rad: 0.35
    allow_fallback_without_map: true
```

Also tighten low TTC lateral gates:

- `pair_in_front.max_lateral_m`: from `4.0` to `2.0`
- `predicate.low_ttc.max_lateral_m`: from `4.0` to `2.0`

Reasoning:

- Same-lane operator is the primary semantic gate.
- The remaining geometry gates should still avoid obviously wide lateral cases.
- Fallback path is intentionally stricter than lane matching.

## Acceptance

- Pair review viewer is ego-centric and stable.
- EGO/TARGET are visually distinguishable.
- `predicate.same_lane_or_path` is registered as a builtin operator.
- Same lane pair passes.
- Adjacent parallel lane pair fails.
- No-map strict same-path fallback can pass.
- Classic `low_ttc_pair` uses `predicate.same_lane_or_path`.
- Existing high-value review rules remain SDC-centric.
