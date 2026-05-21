# Temporal Rule v2 Worker Tasks

This task belongs to `TemporalRuleEngine`, not `EventPolicyEngine`.

## Task 1: AST And Parser

- [x] Extend `SustainedTagCondition` with optional `seconds`.
- [x] Extend `SequenceTagCondition` with optional `within_seconds`.
- [x] Add optional `max_gap_frames` to sequence conditions.
- [x] Parser accepts `sustained.seconds`.
- [x] Parser accepts `sequence.within_seconds`.
- [x] Parser accepts `sequence.max_gap_frames`.
- [x] Parser rejects sustained with both `frames` and `seconds`.
- [x] Parser rejects sequence with both `within_frames` and `within_seconds`.
- [x] Parser rejects non-positive seconds and negative gap.

Acceptance:

- `tests/test_temporal_rule_v2_contract.py::TemporalRuleV2ContractTests.test_parser_supports_seconds_windows_and_gap`
- `tests/test_temporal_rule_v2_contract.py::TemporalRuleV2ContractTests.test_parser_rejects_ambiguous_time_windows`

## Task 2: Compiler

- [x] Preserve source tag validation for seconds-based temporal rules.
- [x] Validate exactly one sustained duration type.
- [x] Validate exactly one sequence window type.
- [x] Validate seconds/gap ranges.

Acceptance:

- Existing compiler tests pass.
- New parser-invalid cases should fail before compile.

## Task 3: Timeline

- [x] Store timestamps by frame in `TagTimeline.from_events`.
- [x] Add `timestamp_at(frame_index)`.
- [x] Add `sustained_seconds(...)`.
- [x] Add `sequence_seconds(...)`.
- [x] Support `max_gap_frames` for sequence matching.

Acceptance:

- `tests/test_temporal_rule_v2_contract.py::TemporalRuleV2ContractTests.test_tag_timeline_matches_sustained_seconds`
- `tests/test_temporal_rule_v2_contract.py::TemporalRuleV2ContractTests.test_tag_timeline_matches_sequence_seconds_with_max_gap`

## Task 4: TemporalRuleEngine

- [x] Evaluate sustained seconds rules.
- [x] Evaluate sequence seconds rules.
- [x] Keep existing frame-based behavior.
- [x] Add supporting timestamp metadata to every temporal event.
- [x] Keep existing metadata keys for backward compatibility.

Acceptance:

- `tests/test_temporal_rule_v2_contract.py::TemporalRuleV2ContractTests.test_trigger_engine_emits_sustained_seconds_event_with_timestamp_metadata`
- `tests/test_temporal_rule_v2_contract.py::TemporalRuleV2ContractTests.test_trigger_engine_emits_sequence_seconds_event_with_timestamp_metadata`

## Task 5: Verification

- [x] Temporal Rule v2 tests pass.
- [x] Full suite passes.

Command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
