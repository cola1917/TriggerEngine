# Sequence Candidate Gating Worker Tasks

## Task 1: Gating Detection

- [x] Identify tags used after the first step in temporal sequences.
- [x] Limit this version to `agent_pair` sequences.
- [x] Exclude sustained source tags.
- [x] Exclude first sequence step tags.
- [x] Resolve gated tags back to their producing single-frame rules.

## Task 2: Filtered Rule Evaluation

- [x] Add `subject_id_filters` to `RuleEngine.evaluate(...)`.
- [x] Add `allowed_subject_ids` to `SubjectCache.subjects_for_rule(...)`.
- [x] Directly construct filtered `agent_pair` subjects from subject ids.

## Task 3: TriggerEngine Integration

- [x] Evaluate ungated single-frame rules first.
- [x] Build timeline from ungated events.
- [x] Evaluate gated rules after predecessor tags are available.
- [x] Rebuild timeline before temporal rule evaluation.
- [x] Emit diagnostics for gated rules.

## Task 4: Contract Tests

- [x] Verify sequence middle steps evaluate only predecessor subject candidates.
- [x] Verify final sequence event is still emitted.
- [x] Verify sustained source tags are not gated.

## Verification

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
