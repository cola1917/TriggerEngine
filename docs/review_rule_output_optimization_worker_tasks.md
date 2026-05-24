# Review Rule Output Optimization Worker Tasks

## Scope

Optimize review event output after the 100-file bulk run.

## Tasks

- [x] Read `docs/review_rule_output_optimization_plan.md`.
- [x] Run the red tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_review_rule_output_optimization_contract -v
```

- [x] Add episode policy to `sdc_repeated_lane_change`.
- [x] Add `review_family` and `review_priority` metadata to:
  - `cut_in_confirmed`
  - `cut_in_risk`
- [x] Extend `EventPolicyEngine` with review dominance after episode policy.
- [x] Dominance only applies to review events with both:
  - `metadata.review_family`
  - numeric `metadata.review_priority`
- [x] Suppress lower-priority same-family events only when intervals overlap.
- [x] Keep lower-priority events when there is no higher-priority overlap.
- [x] Preserve different subjects.
- [x] Add `cooldown_frames: 30` to `sdc_repeated_lane_change` to suppress
  separated non-consecutive review frames.

## Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_review_rule_output_optimization_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_sdc_repeated_lane_change_contract tests.test_cut_in_sequence_contract tests.test_review_episode_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Real Data Check

Run the 100-file scenario-index-0 export again into `review_payload_bulk`.

Expected direction:

```text
sdc_repeated_lane_change review count: 22 -> 2
00035 cut-in review count: confirmed+risk -> risk only
```
