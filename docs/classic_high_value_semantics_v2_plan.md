# Classic High-Value Semantics V2 Plan

## Problem

The classic rule pack is now SDC-scoped, but the high-value review semantics are
still too weak. A review event can be produced by stitching together broad
supporting signals without proving the SDC actually experienced a high-value
scenario.

The known bad pattern is cut-in: an old payload produced `cut_in_confirmed` for
a stationary ego-like vehicle and a nearby moving vehicle. That is not an SDC
cut-in review case. It is a weak geometry coincidence.

## Design Goal

The default classic pack should emit review events only for SDC-centric,
human-reviewable scenarios.

Debug/supporting signals may remain broad enough to explain a rule, but review
events must require stronger semantics.

## Required Upgrades

### 1. Cut-In

Current review path:

```text
adjacent_vehicle -> cut_in_lateral_approach -> same_path_overlap
```

This is not enough. V2 cut-in review must require:

- SDC is moving above a minimum speed.
- Target starts laterally adjacent to the SDC path.
- Target moves laterally toward the SDC path.
- Target ends in the SDC forward corridor.
- The sequence is for the same SDC-target pair.
- Review event is emitted only when the target creates an SDC-relevant risk.

Recommended implementation:

- Add pair operator `predicate.pair_ego_speed_above`.
- Add pair operator `predicate.front_corridor_entry` or tighten existing
  `same_path_overlap` usage with explicit front-only thresholds.
- Apply `predicate.pair_ego_speed_above` to all cut-in review source rules.
- Keep `adjacent_vehicle`, `cut_in_lateral_approach`, and
  `same_path_overlap` as supporting/debug signals.
- Make review-level cut-in prefer `cut_in_risk`.

### 2. Low TTC

Current low-TTC can fire when the SDC is stopped and another object moves toward
it. That is not the intended "SDC behavior/risk" review family for this pack.

V2 low-TTC review must require:

- SDC is moving above a configured minimum speed.
- Target is in front of SDC.
- SDC is closing on the target.
- The low-TTC condition persists.

Recommended implementation:

- Use `predicate.pair_ego_speed_above` in `low_ttc_pair`.
- Configure `predicate.low_ttc.min_closing_speed_mps >= 1.0`.
- Keep `low_ttc_pair` as supporting.
- Keep `persistent_low_ttc_pair` as the review episode.

### 3. Red-Light Running

Current red-light running is a temporal sequence over the SDC subject only:

```text
red_light_stop_line_approach -> red_light_stop_line_crossed
```

Because the subject is only the SDC, the sequence can accidentally combine
signals from different lane ids or stop lines.

V2 red-light review must require:

- Same SDC.
- Same red traffic-light lane id / stop line.
- SDC was before the stop line on red.
- SDC crossed that same stop line while still red.

Recommended implementation:

- Prefer a new operator `predicate.red_light_crossing_transition` that inspects
  the SDC state across the input frame timeline and validates one lane id in one
  place.
- Or extend temporal matching to key source events by metadata, such as
  `lane_id`. The operator path is simpler for this version.

### 4. Stopped Vehicle

Stopped SDC is useful context, but it should not be a high-value review event in
the default classic pack.

Required behavior:

- `sdc_vehicle_stopped*` remain debug/supporting only.
- They must not appear in `review_events`.

## Acceptance

- Existing tests still pass.
- New high-value semantics v2 contract tests pass.
- Static payloads and regenerated real payloads should no longer show review
  cut-in for stationary SDC cases.
- Review events should be fewer but more explainable.
