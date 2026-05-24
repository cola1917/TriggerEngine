# Classic High-Value Semantics V2 Worker Tasks

## Scope

Upgrade the default classic scenario pack so review events are stricter and
SDC-behavior focused.

## Tasks

- [ ] Read `docs/classic_high_value_semantics_v2_plan.md`.
- [ ] Run the red tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_classic_high_value_semantics_v2_contract -v
```

- [ ] Add `predicate.pair_ego_speed_above`.
  - Subject type: `agent_pair`.
  - Uses `subject.ego`.
  - Returns false for invalid ego.
  - Metadata includes observed ego speed and threshold.
- [ ] Register the new operator in `register_builtin_operators`.
- [ ] Update built-in operator contract tests for the new operator.
- [ ] Add SDC moving gate to cut-in review source rules.
- [ ] Ensure stationary SDC cannot emit `cut_in_confirmed` or `cut_in_risk`.
- [ ] Add SDC moving gate to `low_ttc_pair`.
- [ ] Set `predicate.low_ttc.min_closing_speed_mps >= 1.0` in classic YAML.
- [ ] Ensure stationary SDC cannot emit `persistent_low_ttc_pair`.
- [ ] Fix red-light running so temporal matching cannot combine different lane
  ids / stop lines.
  - Preferred: implement `predicate.red_light_crossing_transition`.
  - Alternative: add metadata-keyed sequence matching.
- [ ] Keep stopped SDC tags out of review events.
- [ ] Run targeted tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_classic_high_value_semantics_v2_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_builtin_operators_contract tests.test_cut_in_sequence_contract tests.test_red_light_map_semantics_contract -v
```

- [ ] Run full tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Real Data Check

If Waymo dependencies are available, regenerate:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00000-of-00150 -o review_payload_00000.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00001-of-00150 -o review_payload_00001.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
```

Expected direction:

- Fewer review events.
- No stationary-SDC cut-in review.
- No stationary-SDC persistent low-TTC review.
- Red-light review events must be explainable by one lane id / stop line.
