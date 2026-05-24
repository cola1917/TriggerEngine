# SDC Repeated Lane Change Worker Tasks

## Scope

Implement lane association and the new `sdc_repeated_lane_change` high-value
classic scenario.

Do not implement a highway-specific rule in this version.

## Tasks

- [ ] Read `docs/sdc_repeated_lane_change_plan.md`.
- [ ] Run the red tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sdc_repeated_lane_change_contract -v
```

- [ ] Add reusable lane matching helper, preferably in
  `trigger_engine/operators/lane_matching.py`.
- [ ] Implement nearest-lane matching against lane polylines.
- [ ] Implement `predicate.sdc_lane_changed`.
- [ ] Implement `predicate.sdc_repeated_lane_change`.
- [ ] Register both operators in `register_builtin_operators`.
- [ ] Add `sdc_repeated_lane_change` to `CLASSIC_SCENARIO_RULES_YAML`.
- [ ] Ensure no `sdc_highway_*` rule is added in this version.
- [ ] Preserve current high-value behavior for low TTC, cut-in, and red-light
  running.

## Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sdc_repeated_lane_change_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_classic_high_value_semantics_v2_contract tests.test_cut_in_sequence_contract tests.test_red_light_map_semantics_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Real Data Check

Run the first 10 payloads again:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
for ($i = 0; $i -lt 10; $i++) {
  $suffix = ('{0:D5}' -f $i)
  .\.venv\Scripts\python.exe tools\export_review_payload.py "data\validation_interactive.tfrecord-$suffix-of-00150" -o "review_payload_$suffix.json" --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
}
```

Report:

- total events
- review events
- `sdc_repeated_lane_change` count
- any changed low TTC / cut-in / red-light review counts
