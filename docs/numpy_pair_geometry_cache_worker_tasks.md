# NumPy Pair Geometry Cache Worker Tasks

## Task 1: Environment

- [x] Rebuild project `.venv` with Python 3.12.
- [x] Install `numpy` into project `.venv`.
- [x] Restore required test dependencies `pyyaml` and `protobuf`.

## Task 2: Vectorized Geometry

- [x] Add `PairGeometryCache`.
- [x] Compute pairwise `lon`/`lat` matrices with NumPy.
- [x] Convert masks back to ordered candidate index pairs.

## Task 3: SubjectCache Integration

- [x] Use NumPy path only for large prunable `agent_pair` rules.
- [x] Keep scalar path for small frames.
- [x] Preserve `AgentPairSubject` output.
- [x] Add `rule_geometry_mode(...)` diagnostics.

## Task 4: Contract Tests

- [x] Verify NumPy candidate generation preserves uncached full-scan output.
- [x] Verify large frames use NumPy mode.
- [x] Verify small frames use scalar mode.

## Verification

Run from the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
