# Performance v2 Worker Tasks

## Task 1: Candidate Plan Model

- [x] Add `PairCandidatePredicate`.
- [x] Add `PairCandidatePlan`.
- [x] Derive candidate predicates from existing built-in operator calls.
- [x] Do not add YAML performance parameters.

## Task 2: Subject Cache Integration

- [x] Add `SubjectCache.subjects_for_rule(...)`.
- [x] Build pruned `AgentPairSubject` candidates for supported spatial rules.
- [x] Fall back to full ordered pair cache when no safe predicate exists.
- [x] Keep cache keys scenario-aware.

## Task 3: Rule Engine Integration

- [x] Route cached subject lookup through `subjects_for_rule(...)`.
- [x] Preserve uncached `RuleEngine.evaluate(...)` behavior.

## Task 4: Trigger Engine Integration

- [x] Create a per-evaluate `SubjectCache` by default.
- [x] Preserve injected cache support for tests and diagnostics.

## Task 5: Contract Tests

- [x] Spatial pair rules automatically prune candidates.
- [x] Pruned execution preserves output against uncached execution.
- [x] Unbounded pair rules fall back to the full pair set.
- [x] Default `TriggerEngine` uses candidate pruning without caller parameters.

## Verification

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
