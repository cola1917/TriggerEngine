# Red Light Map Semantics Worker Tasks

This document is the implementation checklist for the worker. The goal is to add
a map-aware red-light-running tag without changing the runtime contract:

```text
AlignmentContext -> active RuleRegistry plan -> TagEvent
```

## Goal

Detect a vehicle crossing a red-light stop line by using:

- dynamic traffic light state from `Frame.traffic_lights`
- traffic-light `lane_id`
- lane centerline from `AlignmentContext.map_features`
- vehicle pose, heading, and speed from `AgentState`

This should be more semantic than the existing `vehicle_stopped_at_red`, which
only checks distance to a red stop point.

## Data Contract

- [x] Add `map_features: dict[int, MapFeature]` to `AlignmentContext`.
- [x] `ScenarioAlignment.align(...)` must propagate `ScenarioBundle.map_features`
  into the returned `AlignmentContext`.
- [x] Existing tests that manually construct `AlignmentContext` must keep working
  by using a default empty map when omitted.

## Required Operators

Add these built-in predicates:

- [x] `predicate.red_light_before_stop_line`
  - subject: `agent`
  - args: `max_lateral_m`, `max_before_stop_line_m`, `min_speed_mps`,
    `max_heading_delta_rad`
  - true when the agent is valid, moving, aligned with the controlled lane, near
    the lane centerline, and still before a red stop point.

- [x] `predicate.red_light_after_stop_line`
  - subject: `agent`
  - args: `max_lateral_m`, `min_after_stop_line_m`, `max_after_stop_line_m`,
    `min_speed_mps`, `max_heading_delta_rad`
  - true when the agent is valid, moving, aligned with the controlled lane, near
    the lane centerline, and past the red stop point.

Both operators should:

- use only traffic lights whose state is `stop` or `arrow_stop`
- require a matching lane map feature by `traffic_light.lane_id`
- compute lane direction from the lane polyline around the stop point when
  possible, otherwise use the first-to-last lane direction
- project `(agent.center - stop_point)` onto lane direction:
  - longitudinal `< 0` means before the stop line
  - longitudinal `> 0` means after the stop line
- return useful metadata: `lane_id`, `longitudinal_m`, `lateral_m`,
  `speed_mps`, and `heading_delta_rad`
- return `False` for invalid agents, missing map, missing stop point, non-red
  traffic lights, or missing lane feature

## YAML Shape

The classic pack should add rules equivalent to:

```yaml
- id: red_light_stop_line_approach
  kind: single_frame
  subject: agent
  when:
    all:
      - operator: predicate.type_is
        args:
          object_type: vehicle
      - operator: predicate.red_light_before_stop_line
        args:
          max_lateral_m: 2.0
          max_before_stop_line_m: 12.0
          min_speed_mps: 0.5
          max_heading_delta_rad: 0.7
  emit:
    tag: red_light_stop_line_approach

- id: red_light_stop_line_crossed
  kind: single_frame
  subject: agent
  when:
    all:
      - operator: predicate.type_is
        args:
          object_type: vehicle
      - operator: predicate.red_light_after_stop_line
        args:
          max_lateral_m: 2.0
          min_after_stop_line_m: 0.5
          max_after_stop_line_m: 15.0
          min_speed_mps: 0.5
          max_heading_delta_rad: 0.7
  emit:
    tag: red_light_stop_line_crossed

- id: red_light_running
  kind: temporal
  subject: agent
  when:
    sequence:
      - tag: red_light_stop_line_approach
      - tag: red_light_stop_line_crossed
    within_frames: 5
  emit:
    tag: red_light_running
```

## Non-Goals

- Do not implement full lane graph traversal.
- Do not infer traffic light state from camera or lidar.
- Do not use future frames.
- Do not mark a stopped vehicle near a red light as running the red light.

## Acceptance

- [x] Alignment context map propagation test passes.
- [x] Built-in red-light map semantic operator tests pass.
- [x] Classic YAML red-light-running contract test passes.
- [x] Classic e2e red-light-running sequence test passes.
- [x] Full test suite passes:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
