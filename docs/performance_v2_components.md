# Performance v2 Components

## PairCandidatePredicate

Location: `trigger_engine/engine/subjects.py`

Represents one safe candidate predicate derived from an existing operator call.
It evaluates relative geometry in the ego frame and returns whether an
`ego, other` pair can still satisfy that operator.

## PairCandidatePlan

Location: `trigger_engine/engine/subjects.py`

```python
@dataclass(frozen=True)
class PairCandidatePlan:
    rule_id: str
    predicates: tuple[PairCandidatePredicate, ...]
```

The plan is built from a rule's `when.all` calls. Multiple predicates are
combined with AND because the rule condition itself is AND.

## SubjectCache

New APIs:

```python
subjects_for_rule(rule, aligned_frame) -> list
rule_build_count(rule_id, subject_type, step_index) -> int
rule_candidate_count(rule_id, subject_type, step_index) -> int
```

Behavior:

- Non-pair subjects use the existing cache path.
- Pair rules with a candidate plan build pruned `AgentPairSubject` instances.
- Pair rules without a candidate plan fall back to the full cached pair list.
- Cache keys include `scenario_id` for generic subjects and `rule_id` for
  pruned pair subjects.

## RuleEngine

When a subject cache is available, `RuleEngine` calls:

```python
subject_cache.subjects_for_rule(rule, aligned_frame)
```

This keeps pruning entirely inside the execution layer. Operators and rule YAML
do not need to know whether pruning happened.

## TriggerEngine

`TriggerEngine.evaluate(...)` creates a per-evaluate `SubjectCache` when one is
not injected. This makes default production-style usage optimized:

```python
subject_cache = self._subject_cache or SubjectCache()
```

## Safety Contract

Candidate pruning is allowed only when the derived predicate is necessary for
the built-in operator to return true. For example:

- `close_lateral_gap`: `abs(lateral) <= max_lateral` and
  `abs(longitudinal) <= max_longitudinal`
- `same_path_overlap`: `abs(lateral) <= max_lateral` and
  `min_longitudinal <= longitudinal <= max_longitudinal`
- `low_ttc`: `abs(lateral) <= max_lateral` and target is in front

If no such predicate exists, the rule must evaluate all ordered valid pairs.
