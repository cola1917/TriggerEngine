# Sequence Candidate Gating Components

## GatedRule

Location: `trigger_engine/engine/trigger_engine.py`

```python
@dataclass(frozen=True)
class GatedRule:
    rule: Rule
    predecessor_tags: tuple[str, ...]
```

`TriggerEngine` derives these from the active execution plan.

## TriggerEngine._gated_rules

Finds single-frame rules that can be evaluated as sequence continuations.

Gating exclusions:

- non-`agent_pair` temporal sequences
- sustained source tags
- first sequence step tags
- tags without a producing single-frame rule

## TriggerEngine.evaluate

Evaluation now has two single-frame phases:

1. Ungated rules run globally.
2. Gated rules run after their predecessor tags are available in the timeline.

For each gated rule, diagnostics are emitted:

```python
EngineDiagnostic(
    level="info",
    message="sequence_candidate_gating",
    metadata={
        "rule_id": ...,
        "tag_name": ...,
        "predecessor_tags": ...,
        "candidate_subjects": ...,
        "events_emitted": ...,
    },
)
```

## RuleEngine Subject Filters

`RuleEngine.evaluate(...)` accepts optional `subject_id_filters`.

```python
subject_id_filters: dict[str, set[str | int | None]]
```

The key is `rule_id`. When present, only matching subjects are evaluated.

## SubjectCache Filtered Subjects

`SubjectCache.subjects_for_rule(...)` accepts `allowed_subject_ids`.

For `agent_pair`, it directly constructs pair subjects from ids such as
`"ego_id:other_id"`, avoiding full pair subject generation.
