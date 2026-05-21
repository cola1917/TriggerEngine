# Temporal Rule v2 Components

## Files

Update:

```text
trigger_engine/rules/ast.py
trigger_engine/rules/parser.py
trigger_engine/engine/compiler.py
trigger_engine/engine/timeline.py
trigger_engine/engine/trigger_engine.py
```

Add tests:

```text
tests/test_temporal_rule_v2_contract.py
```

## Parser

### Sustained

Accept either:

```yaml
sustained:
  frames: 3
```

or:

```yaml
sustained:
  seconds: 1.5
```

Reject both or neither.

### Sequence

Accept either:

```yaml
within_frames: 8
```

or:

```yaml
within_seconds: 2.0
```

Reject both or neither.

Optional:

```yaml
max_gap_frames: 1
```

Reject negative gap.

## Compiler

Keep existing source tag validation.

Additional validation:

- sequence has at least two steps
- sequence has exactly one window type
- sustained has exactly one duration type
- seconds values are positive numbers
- frame/gap values are positive or non-negative integers as appropriate

## TagTimeline

Current `_data` stores presence only:

```python
(tag_name, subject_type, subject_id, frame_index) -> bool
```

Add timestamp support:

```python
_timestamps_by_frame: dict[int, float]
```

Populate it in `from_events`.

### sustained_seconds

For a key and end frame:

1. find matching frames for the key at or before `end_frame_index`
2. walk backward while frames are contiguous by frame index
3. accept when `end_timestamp - first_timestamp >= seconds`

This keeps the first version conservative: sustained seconds still requires
contiguous frames, just measured by time.

### sequence_seconds

For ordered keys:

1. use the end frame timestamp
2. search from earliest events whose timestamp is within
   `[end_timestamp - within_seconds, end_timestamp]`
3. match steps in order for the same subject
4. if `max_gap_frames` is set, require adjacent matched steps to have gap <= max

Return supporting frame indices.

## TemporalRuleEngine Metadata Helper

Add a helper to enrich metadata from supporting frames:

```python
def _with_support_metadata(metadata, timeline, supporting):
    ...
```

The helper should add:

- `supporting_timestamps_seconds`
- `first_matched_frame_index`
- `first_matched_timestamp_seconds`
- `last_matched_frame_index`
- `last_matched_timestamp_seconds`

If a timestamp is missing, use `None` for that position rather than inventing it.

## Backward Compatibility

Existing rules with `within_frames` and `sustained.frames` must keep passing.
Existing event metadata keys must remain present.

