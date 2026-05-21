# Event Policy Worker Tasks

This task adds event post-processing for output stability. It must not change
operator semantics or rule truth evaluation.

Do not implement temporal semantics here. `sequence`, `window`, `within`,
`sustained`, and semantic `hold` belong to the engine temporal rule layer.

## Task 1: AST And Parser

- [x] Add `EventPolicy` dataclass.
- [x] Add `policy: EventPolicy` to `RuleEmit`.
- [x] Parse optional `emit.policy.cooldown_frames`.
- [x] Preserve default behavior when `emit.policy` is omitted.
- [x] Reject invalid policy values with `RuleParseError`.
- [x] Reject unknown `emit.policy` keys.

Acceptance:

- `tests/test_event_policy_contract.py::EventPolicyContractTests.test_rule_parser_reads_emit_cooldown_policy`
- `tests/test_event_policy_contract.py::EventPolicyContractTests.test_rule_parser_rejects_invalid_policy_values`

## Task 2: EventPolicyEngine

- [x] Create `trigger_engine/engine/event_policy.py`.
- [x] Implement `EventPolicyEngine.apply(events, rules)`.
- [x] Apply cooldown by `scenario_id + tag_name + subject_type + subject_id`.
- [x] Preserve event ordering.
- [x] Keep final event timestamp equal to the emitted raw event timestamp.
- [x] Add replay-friendly policy metadata.
- [x] Do not mutate original `TagEvent.metadata`.

Acceptance:

- `tests/test_event_policy_contract.py::EventPolicyContractTests.test_event_policy_engine_applies_cooldown_by_tag_subject`
- `tests/test_event_policy_contract.py::EventPolicyContractTests.test_event_policy_engine_preserves_raw_event_timestamp_for_replay`

## Task 3: TriggerEngine Integration

- [x] Apply policy after single-frame and temporal events are concatenated.
- [x] Build temporal timeline from raw single-frame events, not policy-filtered
  events.
- [x] Update `EngineStats.events_emitted` to final event count.

Acceptance:

- `tests/test_event_policy_contract.py::EventPolicyContractTests.test_trigger_engine_applies_emit_policy_after_temporal_detection`

## Task 4: Full Verification

- [x] Event policy tests pass.
- [x] Full suite passes.

Command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
