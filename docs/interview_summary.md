# Trigger Engine Interview Summary

## Project Positioning

Trigger Engine is a rule-based scenario mining system for autonomous driving
data. It turns large TFRecord road-test style datasets into reviewable
high-value clips by applying configurable trigger rules over ego and target
trajectories, map stop lines, traffic lights, and VRU interactions.

## Why It Matters

Manual replay is slow when useful long-tail cases are sparse. This project
builds a batch mining loop:

```text
raw scenario shard -> trigger mining -> structured summary -> review payload -> HTML viewer -> rule refinement
```

The output is not just a tag count. Each review case keeps scenario id, source
shard, frame index, target id, risk level, subtype, and metrics such as TTC,
relative distance, closing speed, acceleration, and stop-line context.

## Core Technical Design

- Rule DSL: YAML rules define subject type, predicates, temporal composition,
  review intent, and episode policy.
- Operator library: reusable predicates implement kinematics, pair geometry,
  map-aware red-light checks, VRU interaction, hard braking, blocked state, and
  lane-change conflict.
- Engine pipeline: single-frame rules emit `TagEvent`s, temporal rules compose
  them through sustained/sequence logic, and event policy suppresses noisy
  frame-level duplicates.
- Batch workflow: `tools/run_review_batch.py` scans shards, merges summary
  statistics, optionally profiles per-rule cost, and generates viewer payloads.
- Viewer loop: static HTML review pages support fast human validation without a
  backend service.

## High-Value Rules

Current review families:

- `cut_in_confirmed`
- `persistent_low_ttc_pair`
- `red_light_running`
- `sdc_hard_braking`
- `vru_close_interaction`
- `sdc_blocked_unable_to_proceed`
- `lane_change_conflict`

Supporting/debug tags remain available for explanation and temporal logic, but
they are not shown as default review items.

## False-Positive Governance

Important rule refinements:

- Cut-in: suppress ego-turning and stationary-target false positives.
- Red light: reject right-turn style geometry using lane heading and future ego
  heading changes.
- Hard braking: split interaction braking and traffic-light braking subtypes.
- VRU: keep high/medium risk levels and tighten default review to high-value
  close interactions.
- Repeated lane change: kept lower priority; meaningful review focus moved
  toward lane-change conflict.

## Performance Story

The project has a measurable optimization trail:

- SDC-pair generation avoids scanning non-SDC ego pairs.
- Low-TTC candidate generation filters non-closing targets before lane/path
  matching.
- Lane conflict filters stationary/far targets before map matching.
- Lane review rules run on current frames while still using historical windows.
- Red-light checks cache stop-line direction and lane heading change geometry.
- Hard-braking pair generation first checks whether the SDC actually braked.

First-five-shard profiling kept the same review output while improving engine
time from `82.07s` to `9.01s`. The hard-braking gate alone reduced pair scans
from `211557` to `19` for that rule.

## What I Would Emphasize In An Interview

1. I did not start with ML. I built a deterministic mining engine first because
   review recall, explainability, and iteration speed were the bottlenecks.
2. I treated false positives as product debt. Each rule has review semantics,
   risk level, subtype, and metrics to support human validation.
3. I optimized from profiling data, not guesses. Some cache ideas were tested
   and rejected when they made runtime worse.
4. The system forms a closed loop: mine, visualize, inspect, tighten rules, and
   rerun at shard scale.

## Final Validation Plan

Before presenting the project:

- Run all tests.
- Run the first 100 validation shards.
- Keep one final summary JSON and one final viewer HTML.
- Use the final 100-shard counts as the resume/interview number.

## Final 100-Shard Result

The current final run covers the first 100 Waymo validation shards:

- Scanned scenarios: `29023`
- Default review scenarios: `162`
- Payload scenarios including medium candidates: `285`
- Wall time: `703.72s`
- Throughput: `41.24` scenarios/s

Review event distribution:

```text
vru_close_interaction: 73
sdc_blocked_unable_to_proceed: 52
sdc_hard_braking: 42
cut_in_confirmed: 21
persistent_low_ttc_pair: 7
```

Review risk/subtype breakdown:

- `193` high-risk review events
- `2` medium-risk review events
- `49` blocked-by-vehicle cases
- `3` blocked-by-VRU cases
- `40` SDC interaction braking cases
- `2` SDC traffic-light braking cases

Final artifacts:

- `review_batch_v2_final_100.json`
- `review_payload_v2_final_100/`
- `review_viewers_v2_final_100/`
- `view_v2_final_100.html`

The final profile shows the next possible optimization area is red-light
per-frame evaluation and `low_ttc_pair`; however, the project is already
sufficiently complete for an interview narrative because it demonstrates rule
design, false-positive control, batch visualization, and performance profiling.
