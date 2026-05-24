# SDC Repeated Lane Change Plan

## Decision

Add a new high-value review scenario:

```text
sdc_repeated_lane_change
```

Do not add a highway-specific rule in this version. The adapter can carry lane
metadata such as `lane_type` and `speed_limit_mph`, but this version should not
depend on highway/city classification until real-data coverage is verified.

## Why This Scenario

The current high-value pack covers:

- persistent low TTC
- cut-in to SDC
- red-light running

It does not cover SDC's own complex lateral behavior. Repeated lane changes are
high-value because they indicate route complexity, possible aggressive driving,
or challenging lane-selection behavior.

This also builds the missing foundation for later cut-in improvements:
lane association.

## New Map Semantic Layer

Implement lane association as reusable map semantics, not as ad hoc logic inside
one rule.

Recommended module:

```text
trigger_engine/operators/lane_matching.py
```

Public helper:

```python
match_agent_to_lane(agent, map_features, *, max_lateral_m, max_heading_delta_rad)
```

Return shape:

```python
LaneMatch(
    lane_id: int,
    lateral_m: float,
    longitudinal_s_m: float,
    heading_delta_rad: float,
    speed_limit_mph: float | None,
    lane_type: str | None,
)
```

Matching behavior:

- consider only `MapFeature.feature_type == "lane"`
- project agent center onto lane polyline segments
- compute lateral distance to nearest segment
- compute longitudinal distance along lane polyline
- compare agent heading to local segment heading
- reject matches beyond lateral/heading thresholds
- pick the nearest valid lane

## New Operators

### predicate.sdc_lane_changed

Subject: `agent`

Detects whether SDC changed nearest lane between recent frames and current
frame.

Args:

- `window_seconds`
- `max_lateral_m`
- `max_heading_delta_rad`
- `min_speed_mps`

Metadata:

- `previous_lane_id`
- `current_lane_id`
- `previous_frame_index`
- `current_frame_index`
- `lane_sequence`

### predicate.sdc_repeated_lane_change

Subject: `agent`

Detects at least `min_lane_changes` nearest-lane changes in the recent window.

Args:

- `window_seconds`
- `min_lane_changes`
- `max_lateral_m`
- `max_heading_delta_rad`
- `min_speed_mps`

Metadata:

- `lane_sequence`
- `lane_change_count`
- `matched_frame_indices`
- `matched_timestamps_seconds`

## Classic Rule

Add to `CLASSIC_SCENARIO_RULES_YAML`:

```yaml
- id: sdc_repeated_lane_change
  kind: single_frame
  subject: sdc_agent
  when:
    all:
      - operator: predicate.type_is
        args:
          object_type: vehicle
      - operator: predicate.sdc_repeated_lane_change
        args:
          window_seconds: 3.0
          min_lane_changes: 2
          max_lateral_m: 1.5
          max_heading_delta_rad: 0.7
          min_speed_mps: 2.0
  emit:
    tag: sdc_repeated_lane_change
    intent: review
    policy:
      cooldown:
        seconds: 3.0
```

## Boundaries

This rule should not fire when:

- there is no map
- lane matching is ambiguous or too far from all lanes
- SDC only jitters around one lane center
- SDC changes once but not repeatedly
- SDC is stopped or creeping below `min_speed_mps`

## Future Highway Extension

After real-data inspection confirms stable metadata coverage, add a separate
rule:

```text
sdc_highway_repeated_lane_change
```

That rule can require:

- `lane_type == freeway`, or
- `speed_limit_mph >= 45/55`

Do not add this in the current version.
