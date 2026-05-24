# Classic SDC-Only Rule Pack Worker Tasks

## Status

Pending worker implementation.

## Task 1: Convert All Classic Subjects to SDC

- [ ] Ensure every rule in `CLASSIC_SCENARIO_RULES_YAML` uses either
  `sdc_agent` or `sdc_pair`.
- [ ] Remove generic `agent` / `agent_pair` subjects from the classic pack.
- [ ] Keep operator compatibility through existing SDC subject support.

## Task 2: Rename Stopped Rules and Tags

- [ ] Rename `vehicle_stopped` to `sdc_vehicle_stopped`.
- [ ] Rename emitted tag `vehicle_stopped` to `sdc_vehicle_stopped`.
- [ ] Rename `vehicle_stopped_for_3_frames` to
  `sdc_vehicle_stopped_for_3_frames`.
- [ ] Rename emitted tag `vehicle_stopped_for_3_frames` to
  `sdc_vehicle_stopped_for_3_frames`.
- [ ] Rename `vehicle_stopped_at_red` to `sdc_vehicle_stopped_at_red`.
- [ ] Rename emitted tag `vehicle_stopped_at_red` to
  `sdc_vehicle_stopped_at_red`.
- [ ] Rename `vehicle_still_stopped_at_red` to
  `sdc_vehicle_still_stopped_at_red`.
- [ ] Rename emitted tag `vehicle_still_stopped_at_red` to
  `sdc_vehicle_still_stopped_at_red`.
- [ ] Update temporal source tags to reference the renamed tags.

## Task 3: Cut-In and Low TTC Review Cleanup

- [ ] Convert `cut_in_candidate` and `cut_in_developing` to `sdc_pair`.
- [ ] Add episode policy to `cut_in_confirmed`.
- [ ] Add episode policy to `cut_in_risk`.
- [ ] Tighten low TTC `predicate.pair_in_front.min_longitudinal_m` to `1.0`
  or higher.

## Task 4: Tests and Real Data

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_classic_sdc_only_rule_pack_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Real-data check:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00000-of-00150 -o review_payload_00000.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00001-of-00150 -o review_payload_00001.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
```

Expected:

- Payload tag names no longer include generic `vehicle_stopped`.
- All classic review/supporting/debug emissions are SDC-scoped.
- `00000` and `00001` may have zero review events if SDC is not in a high-value
  scenario; that is acceptable.
