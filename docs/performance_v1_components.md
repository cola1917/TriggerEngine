# Performance v1 Components

## SubjectCache

Add:

```text
trigger_engine/engine/subjects.py
```

Suggested API:

```python
class SubjectCache:
    def subjects_for(self, subject_type: str, aligned_frame) -> tuple[object, ...]:
        ...

    def subject_id(self, subject_type: str, subject) -> str | int | None:
        ...
```

Requirements:

- cache key: `(aligned_frame.frame.step_index, subject_type)`
- return immutable tuples so callers do not mutate cached subjects
- support existing subject types:
  - `agent`
  - `frame`
  - `lane`
  - `scenario`
  - `agent_pair`
- `agent_pair` must preserve current ordered pair semantics:
  - valid agents only
  - no self-pairs
  - subject id remains `"ego_id:other_id"`

Both `RuleEngine` and `TemporalRuleEngine` should use the same cache instance
for one `TriggerEngine.evaluate(...)` call.

## RuleEngine

Change constructor or evaluate signature to accept a subject cache:

```python
RuleEngine.evaluate(rule_set, context, subject_cache=None)
```

If no cache is provided, create one for backward compatibility.

RuleEngine must not call its old `_get_subjects` repeatedly for the same frame
and subject type once a cache is available.

## TagTimeline Indexes

Current presence map stays:

```python
(tag_name, subject_type, subject_id, frame_index) -> bool
```

Add:

```python
(tag_name, subject_type, subject_id) -> sorted tuple[int, ...]
(tag_name, subject_type) -> set[subject_id]
frame_index -> timestamp_seconds
```

Suggested API:

```python
def subject_ids_for(self, tag_name: str, subject_type: str) -> tuple[str | int | None, ...]

def frames_for(self, key: TagKey) -> tuple[int, ...]

def candidate_end_frames(self, keys: tuple[TagKey, ...]) -> tuple[int, ...]
```

`candidate_end_frames` can start simple:

- sustained: frames from source tag
- sequence: frames from last source tag

## TemporalRuleEngine

Temporal engine should not generate all subjects.

For sustained:

```text
candidate subject ids = timeline.subject_ids_for(source_tag, subject_type)
candidate end frames = timeline.frames_for(source_tag + subject)
```

For sequence:

```text
candidate subject ids = intersection of subject ids for each sequence step
candidate end frames = frames for the last sequence step
```

Then call existing `sustained`, `sustained_seconds`, `sequence`, or
`sequence_seconds` only for those candidate keys/end frames.

The emitted event timestamp should use `timeline.timestamp_at(end_frame_index)`.

## Correctness Contract

Output must remain identical for existing tests:

- same tags
- same frame indices
- same subject ids
- same metadata
- same event ordering where deterministic today

## Instrumentation

Add optional lightweight counters for tests:

```python
SubjectCache.stats = {
    "builds": {("agent_pair", frame_index): 1, ...}
}
```

or expose:

```python
cache.build_count(subject_type, frame_index)
```

This lets tests assert that `agent_pair` is built once per frame, not once per
rule.

