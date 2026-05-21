# Performance v3 Worker Tasks

## Task 1: Spatial Broad Phase

- [x] Add a cheap squared-distance radius filter for bounded pair rules.
- [x] Preserve ordered output by keeping the original ordered pair traversal.

## Task 2: Candidate Plan Radius

- [x] Derive finite search radii from bounded spatial operators.
- [x] Use the smallest finite radius when multiple bounded predicates exist.
- [x] Fall back to full pair scan when no finite radius exists.

## Task 3: Diagnostics

- [x] Add `rule_pair_scan_count(...)` for tests and performance inspection.
- [x] Keep existing v1/v2 diagnostic methods compatible.

## Task 4: Contract Tests

- [x] Verify bounded pair rules scan far fewer pairs than full `N^2`.
- [x] Verify spatial broad-phase execution preserves outputs against uncached full scan.

## Verification

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
