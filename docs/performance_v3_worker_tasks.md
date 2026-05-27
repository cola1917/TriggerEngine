# Performance v3 Worker Tasks

## Task 1: Spatial Broad Phase

- [x] Add a cheap squared-distance radius filter for bounded pair rules.
- [x] Preserve ordered output by keeping the original ordered pair traversal.

## Task 2: Candidate Plan Radius

- [x] Derive finite search radii from bounded spatial operators.
- [x] Use the smallest finite radius when multiple bounded predicates exist.
- [x] Fall back to full pair scan when no finite radius exists.

## Task 3: Diagnostics

- [x] Add `rule_pair_scan_count(...)` for tests and performance inspection.
- [x] Keep existing v1/v2 diagnostic methods compatible.

## Task 4: Contract Tests

- [x] Verify bounded pair rules scan far fewer pairs than full `N^2`.
- [x] Verify spatial broad-phase execution preserves outputs against uncached full scan.

## Task 5: SDC Pair Candidate Evaluation

- [x] Generate `sdc_pair` candidates as `SDC -> target` in `SubjectCache`.
- [x] Skip `only_current_frame` rules before subject generation.
- [x] Verify first-five-shard review output is unchanged.
- [x] Record benchmark: wall time `33.86s -> 29.51s`, engine time `82.07s -> 61.93s`.

## Deferred: Adapter Optimization

- [ ] Keep Waymo adapter changes out of this phase.
- [ ] Revisit adapter light-parsing only after rule-level profiling identifies
  the remaining engine-side ceiling.

## Next: Batch Workflow and Rule Profiling

- [x] Add a summary-first batch mode for large runs.
- [x] Add optional per-rule profiling fields: candidate count, scan count,
  emitted count, and elapsed seconds.
- [x] Use first-five-shard profiling output to identify current slow rules:
  `low_ttc_pair`, `lane_change_conflict`, and `sdc_repeated_lane_change`.
- [x] Optimize `low_ttc_pair` with closing-speed candidate gating and cheap
  predicate ordering before lane/path matching.
- [x] Optimize `lane_change_conflict` with moving-target candidate gating and
  cheap relative-position checks before lane matching.
- [x] Run expensive lane-review rules only on current frames and add a raw SDC
  lateral-displacement gate before lane matching.
- [x] Verify first-five-shard review output is unchanged after lane-review
  narrowing.
- [x] Cache red-light stop-line directions and lane heading change checks.
- [x] Verify first-five-shard review output is unchanged after red-light
  geometry caching.
- [x] Add an SDC hard-braking motion gate before pair candidate generation.
- [x] Verify first-five-shard review output is unchanged after hard-braking
  gating.
- [ ] Use profiling output to decide whether `low_ttc_pair` or adapter/alignment
  need the next optimization pass.

## Verification

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
