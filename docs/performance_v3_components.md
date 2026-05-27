# Performance v3 Components

## Spatial Broad Phase

Location: `trigger_engine/engine/subjects.py`

For bounded pair rules, candidate generation first applies a cheap
world-coordinate squared-distance check:

```python
dx = other.center.x - ego.center.x
dy = other.center.y - ego.center.y
if dx * dx + dy * dy > radius_sq:
    continue
```

This avoids the more expensive ego-frame rotation and predicate checks for far
pairs while preserving the original ordered pair traversal.

## PairCandidatePlan.search_radius_m

Finite radii are derived from bounded spatial operators:

- `predicate.close_lateral_gap`
- `predicate.lateral_gap_between`
- `predicate.same_path_overlap`

The radius is `sqrt(max_lateral_m^2 + max_longitudinal_m^2)`. If a rule has
multiple finite predicates, the smallest radius is safe because all predicates
must be true.

## SubjectCache Diagnostics

New diagnostic API:

```python
rule_pair_scan_count(rule_id, subject_type, step_index) -> int
```

This reports how many ordered candidate pairs reached exact candidate predicate
checking after the broad-phase radius filter.

## Fallback

If `PairCandidatePlan.search_radius_m` is `None`, `SubjectCache` keeps the v2
full ordered scan plus exact candidate predicates.

## Current Benchmark Conclusion

Baseline after the blocked-trigger tightening, on the first five full Waymo
validation shards:

- Input: `1445` scenarios from shards `00000` through `00004`
- Workers: `5`
- Output mode: summary plus payload JSON and review HTML
- Review output: `8` review scenarios
- Wall time before SDC-pair optimization: `33.86s`
- Wall time after SDC-pair optimization: `29.51s`
- Engine time after optimization: `61.93s`, down from `82.07s`

The review result stayed unchanged:

- `sdc_blocked_unable_to_proceed`: `5`
- `cut_in_confirmed`: `1`
- `sdc_hard_braking`: `1`
- `vru_close_interaction`: `1`

The observed five-shard runtime projects to roughly `9-12` minutes for
`100` shards with the same worker count and payload/view generation enabled.
This is acceptable for review batches but still too slow for rapid parameter
iteration.

## Next Optimization Boundary

Do not optimize the Waymo adapter yet. The adapter is expensive, but changing
it risks altering decoded scenario semantics. Keep adapter work for a later
phase after rule-side and batch workflow bottlenecks are measured more
precisely.

The next safe areas are:

- Engineering workflow: run large batches summary-first, then generate payloads
  and HTML only for selected review scenarios.
- Per-rule profiling: measure candidate counts, scan counts, hit counts, and
  rule-level elapsed time to identify the remaining slow rules inside the
  engine.

## Summary-First Batch Workflow

Large batches can now run without payload/view generation:

```powershell
E:\code\TriggerEngine\.venv\Scripts\python.exe tools\run_review_batch.py `
  data\validation_interactive.tfrecord-00000-of-00150 `
  --workers 5 `
  --profile-rules `
  --output review_batch_summary.json
```

Payloads and the HTML index can be generated later from the saved summary:

```powershell
E:\code\TriggerEngine\.venv\Scripts\python.exe tools\run_review_batch.py `
  --from-summary review_batch_summary.json `
  --output review_batch_with_payloads.json `
  --payload-dir review_payloads `
  --view-output view.html `
  --viewer-dir review_viewers
```

The second phase uses `review_scenario_refs`, so it generates primary review
scenarios only. This is intentional for large-scale review triage.

## First Profiling Result

On the first five shards with summary-only profiling enabled, review output
remained unchanged while rule-level profiling identified the current slowest
engine rules:

- `low_ttc_pair`: `29.24s`, `558562` pair scans, `19075` candidates
- `lane_change_conflict`: `15.83s`, `124968` pair scans, `18829` candidates
- `sdc_repeated_lane_change`: `8.41s`, SDC-agent lane matching

The next code-level optimization should start with `low_ttc_pair` candidate
gating or cheaper lane/path filtering, then revisit lane-change map matching.

## TTC and Conflict Candidate Gating

The first follow-up optimization kept review output unchanged and moved cheap
kinematic gates before expensive lane/path matching:

- `low_ttc_pair` now candidate-filters by closing speed before rule evaluation.
- `low_ttc_pair` evaluates front/TTC predicates before `same_lane_or_path`.
- `lane_change_conflict` filters stationary targets in candidate generation.
- `lane_change_conflict` checks relative position and target speed before lane
  matching.

First-five-shard profile after this pass:

- Review output stayed unchanged at `8` review scenarios.
- Engine time improved from `61.89s` to `53.97s`.
- `low_ttc_pair` improved from `29.24s` to `2.24s`.
- `lane_change_conflict` candidates dropped from `18829` to `8482`.

The remaining dominant costs are lane matching in `lane_change_conflict` and
`sdc_repeated_lane_change`. Further optimization should focus on lane-match
reuse or on narrowing/removing repeated lane-change review semantics.

## Lane Review Lateral Gate

The second follow-up optimization kept the lane-review semantics but reduced
unnecessary map matching:

- `lane_change_conflict` and `sdc_repeated_lane_change` now run only on the
  scenario current frame, while still looking back across their configured
  motion window.
- Both operators first compute a cheap SDC lateral displacement range from raw
  trajectory points. If the SDC never moves laterally enough to satisfy the
  existing threshold, expensive lane matching is skipped.

First-five-shard profile after this pass:

- Review output stayed unchanged at `8` review scenarios.
- Engine time improved from `53.97s` to `27.57s`.
- `lane_change_conflict` improved to `0.28s`.
- `sdc_repeated_lane_change` improved to `0.14s`.

After this pass, the dominant engine-side costs moved away from lane review
rules and back to red-light map checks, `low_ttc_pair`, and hard-braking pair
generation.

## Red-Light Geometry Cache

The third follow-up optimization added scenario-local caches for repeated
red-light geometry:

- `_find_red_light_and_lane` now caches red-light stop-line lane directions per
  frame.
- `red_light_crossing_transition` now caches lane heading change checks per
  lane stop point and lookahead distance.

First-five-shard profile after this pass:

- Review output stayed unchanged at `8` review scenarios.
- Engine time improved slightly from `27.57s` to `26.67s`.
- `red_light_stop_line_crossed` improved from `5.89s` to `5.02s`.
- `red_light_running` improved from `5.38s` to `4.56s`.

The modest gain suggests the remaining red-light cost is dominated by per-frame
rule evaluation and future heading scans, not only stop-line geometry.

## SDC Hard-Braking Motion Gate

The fourth follow-up optimization moved the ego hard-braking check ahead of
pair candidate generation for `sdc_hard_braking`:

- `SubjectCache` detects rules with `predicate.pair_ego_hard_braking`.
- For `sdc_pair` rules, it computes the SDC speed drop and acceleration once
  per frame before scanning targets.
- If the SDC did not hard brake, the rule returns zero pair candidates for that
  frame. If the SDC did hard brake, the existing target, spatial, red-light,
  and review-subtype logic runs unchanged.

First-five-shard profile after this pass:

- Review output stayed unchanged at `8` review scenarios.
- Engine time improved from `26.67s` to `9.01s`.
- `sdc_hard_braking` improved from `2.66s` to `0.22s`.
- `sdc_hard_braking` pair scans dropped from `211557` to `19`.
- `sdc_hard_braking` candidates dropped from `26798` to `2`.

After this pass, the dominant engine-side rule is `low_ttc_pair`; remaining
large wall-clock cost is mostly adapter/alignment dominated for the first-five
shard run.
