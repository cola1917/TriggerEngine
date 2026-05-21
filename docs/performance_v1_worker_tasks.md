# Performance v1 Worker Tasks

This task is a pure performance pass. Do not change rule semantics or tag output.

## Task 1: Subject Cache

- [x] Add `trigger_engine/engine/subjects.py`.
- [x] Implement `SubjectCache`.
- [x] Cache subjects by `(frame_index, subject_type)`.
- [x] Preserve existing ordered `agent_pair` semantics.
- [x] Expose testable build counts.
- [x] Update `RuleEngine` to use the cache.
- [x] Keep backward compatibility for direct `RuleEngine.evaluate(...)` calls.

Acceptance:

- `tests/test_performance_v1_contract.py::PerformanceV1ContractTests.test_subject_cache_builds_agent_pairs_once_per_frame`
- `tests/test_performance_v1_contract.py::PerformanceV1ContractTests.test_rule_engine_reuses_subject_cache_across_pair_rules`

## Task 2: TagTimeline Indexes

- [x] Store frames by `(tag_name, subject_type, subject_id)`.
- [x] Store subject ids by `(tag_name, subject_type)`.
- [x] Add `frames_for(TagKey)`.
- [x] Add `subject_ids_for(tag_name, subject_type)`.
- [x] Keep existing `has_at`, `sustained`, `sequence`, `sustained_seconds`,
  and `sequence_seconds` behavior compatible.

Acceptance:

- `tests/test_performance_v1_contract.py::PerformanceV1ContractTests.test_tag_timeline_exposes_indexed_subjects_and_frames`

## Task 3: Temporal Candidate Evaluation

- [x] Rewrite temporal sustained evaluation to use timeline subject/frame
  candidates.
- [x] Rewrite temporal sequence evaluation to use timeline subject/frame
  candidates.
- [x] Do not generate all `agent_pair` subjects in temporal evaluation.
- [x] Preserve temporal metadata.

Acceptance:

- `tests/test_performance_v1_contract.py::PerformanceV1ContractTests.test_temporal_engine_does_not_build_all_agent_pairs_for_sequence_rules`
- Existing temporal tests pass.

## Task 4: Equivalence And Full Verification

- [x] Existing classic scenario output remains unchanged.
- [x] Full test suite passes.
- [x] Optional: run the first 20 real scenarios and report average/max engine
  time before/after.

Command:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
