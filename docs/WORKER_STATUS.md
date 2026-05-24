# Worker Status Board

This file is the shared handoff board between designer/reviewer and worker.

## Workflow

1. Designer writes the next assignment in `Designer Handoff`.
2. Worker implements the assignment.
3. Worker writes a concise completion note in `Worker Update`.
4. Reviewer checks:
   - this file diff
   - code diff
   - targeted tests
   - full tests when needed
   - real-data output when the task affects viewer/payload behavior
5. Reviewer writes the result in `Review Result`.

## Current Assignment

Status: Accepted.

### Designer Handoff

Implement Low TTC Lane Semantics And Ego-Centric Viewer.

Design plan:

- `docs/low_ttc_lane_semantics_and_ego_view_plan.md`

Worker checklist:

- `docs/low_ttc_lane_semantics_and_ego_view_worker_tasks.md`

Problem:

- Pair-event viewer framing does not keep EGO visually fixed, so EGO/TARGET
  and front/back relations are hard to review.
- `low_ttc_pair` is SDC-centric but not lane-aware. It can still accept
  adjacent-lane vehicles because lateral gates are currently loose geometry.

Required behavior:

- Add builtin pair operator `predicate.same_lane_or_path`.
- Use lane matching when map lanes are available.
- Reject adjacent parallel lanes when both agents match different lane ids.
- Allow strict same-path fallback only when lane matching is unavailable.
- Add `predicate.same_lane_or_path` to `low_ttc_pair`.
- Tighten low TTC lateral gates to `<= 2.0m`.
- Update pair-event viewer transform to center and rotate by EGO.
- Keep EGO/TARGET labels and summary readable.

Verification command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_low_ttc_lane_semantics_contract tests.test_review_viewer_ego_centric_contract -v
```

Resolved expected failures:

- `predicate.same_lane_or_path` is registered.
- `low_ttc_pair` uses the lane/same-path gate.
- Viewer `eventFrameTransform` uses EGO position and heading for pair events.
- Projection anchors EGO lower in the canvas.

Verification commands:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_low_ttc_lane_semantics_contract tests.test_review_viewer_ego_centric_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_builtin_operators_contract tests.test_classic_sdc_only_rule_pack_contract tests.test_review_viewer_v2_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Real-data verification:

After implementation, regenerate representative review payloads if practical,
then render the index:

```powershell
.\.venv\Scripts\python.exe tools\render_review_index.py review_payload_bulk -o view.html
```

Review low TTC files manually: EGO should stay fixed and TARGET should appear in
front of EGO. Adjacent-lane-looking low TTC events should drop after payload
regeneration.

### Worker Update

Done.

Changes made:

1. `trigger_engine/operators/builtins.py` — Added `SameLaneOrPathOperator`
   (`predicate.same_lane_or_path`). Lane-matches both agents via
   `match_agent_to_lane`; returns true only when same lane id. Falls back to
   strict same-path geometry only when no map lanes are available.

2. `trigger_engine/scenarios/classic.py` — Added `predicate.same_lane_or_path`
   gate to `low_ttc_pair`. Tightened `pair_in_front.max_lateral_m` and
   `predicate.low_ttc.max_lateral_m` from 4.0 to 2.0.

3. `tools/export_viewer.py` — Updated viewer JS:
   - Added `pairRoleIds`, `egoAgentForEvent`, `targetAgentForEvent` helpers.
   - `eventFrameTransform` now anchors on EGO for `agent_pair` events
     (cx/heading from ego, radius 45, anchor y=0.68).
   - `project` uses `transform.anchor` for screen placement.
   - `roleForAgent` uses explicit pair id lookup.

4. `tests/test_builtin_operators_contract.py` — Added `predicate.same_lane_or_path`
   to expected operator names.

7/7 contract tests pass. Full suite: 216/216 pass.

### Review Result

Accepted.

Reviewer notes:

- Inspected `docs/WORKER_STATUS.md` and implementation diff.
- Confirmed `predicate.same_lane_or_path` was added and registered.
- Confirmed `low_ttc_pair` now includes `predicate.same_lane_or_path`.
- Confirmed low TTC lateral gates are tightened to `2.0m`.
- Confirmed viewer JS now has:
  - `pairRoleIds`
  - `egoAgentForEvent`
  - `targetAgentForEvent`
  - EGO-centered `eventFrameTransform`
  - anchored projection using `transform.anchor`
- Targeted tests pass: 7/7.
- Builtin/classic/viewer regression tests pass: 33/33.
- Full test suite passes: 216/216.
- Existing `review_payload_bulk` index still renders to `view.html`.

Real-data spot check after regenerating three representative payloads:

```text
review_payload_00003.json: review 0
review_payload_00010.json: review 0
review_payload_00035.json: review 1, cut_in_confirmed 1
```

Interpretation:

- Prior low-TTC review cases in `00003` and `00010` drop after the
  same-lane/same-path gate.
- `00035` no longer emits `cut_in_risk`; it keeps `cut_in_confirmed`, which is
  expected because risk now depends on stricter low TTC semantics.

## Review Checklist

- [x] Read `docs/WORKER_STATUS.md` first.
- [x] Inspect code diff.
- [x] Run low TTC lane semantics tests.
- [x] Run ego-centric viewer tests.
- [x] Run existing builtin/classic/viewer regression tests.
- [x] Run full tests if changes are broad.
- [x] Render `review_payload_bulk` into `view.html`.
- [x] Verify low TTC representative outputs dropped after lane gate.
- [x] Report pass/fail and any next fix.
