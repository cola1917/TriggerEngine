# Low TTC Lane Semantics And Ego-Centric Viewer Worker Tasks

## Assignment

Implement ego-centric pair-event visualization and tighten low TTC to same-lane
or strict same-path semantics.

Design:

- `docs/low_ttc_lane_semantics_and_ego_view_plan.md`

## Checklist

- [x] Add builtin operator `predicate.same_lane_or_path`.
- [x] Register the operator in `register_builtin_operators`.
- [x] Add lane-aware logic using `trigger_engine/operators/lane_matching.py`.
- [x] Ensure adjacent parallel lanes return false when both agents lane-match.
- [x] Allow strict no-map fallback only when lane matching is unavailable.
- [x] Update `CLASSIC_SCENARIO_RULES_YAML` so `low_ttc_pair` uses
      `predicate.same_lane_or_path`.
- [x] Tighten low TTC lateral gates from `4.0` to `2.0`.
- [x] Update viewer `eventFrameTransform` so `agent_pair` events are centered
      and rotated by EGO, not pair average or target heading.
- [x] Keep EGO/TARGET summary and visual labels.
- [x] Run targeted and regression tests.

## Test Commands

Targeted tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_low_ttc_lane_semantics_contract tests.test_review_viewer_ego_centric_contract -v
```

Regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_builtin_operators_contract tests.test_classic_sdc_only_rule_pack_contract tests.test_review_viewer_v2_contract -v
```

Full suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Real-Data Check

After implementation, regenerate or rerun review payloads for the existing bulk
set if practical:

```powershell
.\.venv\Scripts\python.exe tools\render_review_index.py review_payload_bulk -o view.html
```

Then inspect low TTC review files:

- EGO should be visually fixed in the viewer.
- TARGET should appear in front of EGO for low TTC.
- Adjacent-lane-looking low TTC cases should drop after payload regeneration.
