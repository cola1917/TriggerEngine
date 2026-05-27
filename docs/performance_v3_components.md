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
