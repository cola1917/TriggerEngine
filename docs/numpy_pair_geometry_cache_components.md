# NumPy Pair Geometry Cache Components

## PairGeometryCache

Location: `trigger_engine/engine/subjects.py`

```python
class PairGeometryCache:
    MIN_VECTOR_AGENT_COUNT = 32
    def candidate_index_pairs(plan: PairCandidatePlan) -> list[tuple[int, int]]
```

It stores valid agent positions and headings as arrays, then builds:

- `dx = other_x - ego_x`
- `dy = other_y - ego_y`
- `lon = dx * cos(ego_heading) + dy * sin(ego_heading)`
- `lat = -dx * sin(ego_heading) + dy * cos(ego_heading)`

The resulting masks are converted back into ordered `(ego_index, other_index)`
pairs. `SubjectCache` then creates normal `AgentPairSubject` objects.

## Supported Candidate Predicates

The vectorized path supports the same candidate predicates as the scalar path:

- `predicate.close_lateral_gap`
- `predicate.lateral_gap_between`
- `predicate.same_path_overlap`
- `predicate.pair_in_front`
- `predicate.low_ttc`

`lateral_gap_between` remains a broad candidate predicate, matching the scalar
path: it applies the max lateral/longitudinal bounds and leaves the min-lateral
business condition to the real operator.

## SubjectCache Integration

`SubjectCache._build_agent_pair_candidates(...)` now chooses:

- NumPy path for large prunable pair rules
- scalar path for small frames or non-prunable rules

Existing diagnostics are preserved, and `rule_geometry_mode(...)` was added for
tests and performance inspection.
