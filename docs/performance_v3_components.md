# Performance v3 Components

## Spatial Broad Phase

Location: `trigger_engine/engine/subjects.py`

For bounded pair rules, candidate generation first applies a cheap
world-coordinate squared-distance check:

```python
dx = other.center.x - ego.center.x
dy = other.center.y - ego.center.y
if dx * dx + dy * dy > radius_sq:
    continue
```

This avoids the more expensive ego-frame rotation and predicate checks for far
pairs while preserving the original ordered pair traversal.

## PairCandidatePlan.search_radius_m

Finite radii are derived from bounded spatial operators:

- `predicate.close_lateral_gap`
- `predicate.lateral_gap_between`
- `predicate.same_path_overlap`

The radius is `sqrt(max_lateral_m^2 + max_longitudinal_m^2)`. If a rule has
multiple finite predicates, the smallest radius is safe because all predicates
must be true.

## SubjectCache Diagnostics

New diagnostic API:

```python
rule_pair_scan_count(rule_id, subject_type, step_index) -> int
```

This reports how many ordered candidate pairs reached exact candidate predicate
checking after the broad-phase radius filter.

## Fallback

If `PairCandidatePlan.search_radius_m` is `None`, `SubjectCache` keeps the v2
full ordered scan plus exact candidate predicates.
