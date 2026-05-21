# Temporal Rule v2 Architecture

## Purpose

Temporal Rule v2 adds business time semantics to `TemporalRuleEngine`.

This is separate from `EventPolicyEngine`:

```text
TemporalRuleEngine: decides whether a time-based event is true
EventPolicyEngine: decides whether an already-true event should be emitted again
```

Examples that belong here:

- overtake completed within 5 seconds
- red-light stop line crossed within 1 second of approach
- low TTC sustained for 1.5 seconds
- cut-in sequence allowing one missing frame between supporting tags

## MVP Scope

Add:

- `sequence.within_seconds`
- `sustained.seconds`
- optional `max_gap_frames` for sequence matching
- temporal event metadata with supporting timestamps

Keep existing support:

- `sequence.within_frames`
- `sustained.frames`

Do not implement:

- arbitrary CEP
- nested temporal expressions
- cross-subject mapping such as `agent_pair.ego -> agent`
- post-processing cooldown/hold behavior

## YAML Examples

### Sequence Within Seconds

```yaml
- id: overtake_completed
  kind: temporal
  subject: agent_pair
  when:
    sequence:
      - tag: overtake_started
      - tag: overtake_side_by_side
      - tag: overtake_ahead
    within_seconds: 5.0
  emit:
    tag: overtake_completed
```

### Sustained Seconds

```yaml
- id: stopped_for_1_5s
  kind: temporal
  subject: agent
  when:
    tag: vehicle_stopped
    sustained:
      seconds: 1.5
  emit:
    tag: stopped_for_1_5s
```

### Sequence With Gap Tolerance

```yaml
- id: noisy_cut_in
  kind: temporal
  subject: agent_pair
  when:
    sequence:
      - tag: adjacent_vehicle
      - tag: same_path_overlap
    within_seconds: 2.0
    max_gap_frames: 1
  emit:
    tag: noisy_cut_in
```

`max_gap_frames` limits gaps between matched sequence steps. If step A matches at
frame 10 and step B matches at frame 13, then the gap is `13 - 10 - 1 = 2`.

## AST Changes

```python
@dataclass(frozen=True)
class SustainedTagCondition:
    tag_name: str
    frames: int | None = None
    seconds: float | None = None

@dataclass(frozen=True)
class SequenceTagCondition:
    steps: tuple[SequenceStep, ...]
    within_frames: int | None = None
    within_seconds: float | None = None
    max_gap_frames: int | None = None
```

Validation:

- sustained must define exactly one of `frames` or `seconds`
- sequence must define exactly one of `within_frames` or `within_seconds`
- `frames > 0`
- `seconds > 0`
- `max_gap_frames >= 0` when present

## Timeline Changes

`TagTimeline` should preserve timestamps:

```python
def timestamp_at(self, frame_index: int) -> float | None

def sustained_seconds(
    self,
    key: TagKey,
    end_frame_index: int,
    seconds: float,
) -> tuple[bool, tuple[int, ...]]

def sequence_seconds(
    self,
    keys: tuple[TagKey, ...],
    end_frame_index: int,
    within_seconds: float,
    max_gap_frames: int | None = None,
) -> tuple[bool, tuple[int, ...]]
```

The timeline can learn frame timestamps from `TagEvent.timestamp_seconds`.
Because temporal rules are evaluated only over frames that have source tag events,
this is sufficient for MVP.

## Metadata Contract

Every temporal event should include:

```python
{
    "rule_kind": "temporal",
    "temporal_kind": "sequence" | "sustained",
    "supporting_frame_indices": (...),
    "supporting_timestamps_seconds": (...),
    "first_matched_frame_index": ...,
    "first_matched_timestamp_seconds": ...,
    "last_matched_frame_index": ...,
    "last_matched_timestamp_seconds": ...,
}
```

Existing metadata such as `source_tag`, `source_tags`, `within_frames`,
`within_seconds`, `sustained_frames`, or `sustained_seconds` should remain.

## Engine Integration

`TriggerEngine` already builds temporal rules from the raw single-frame timeline.
That stays unchanged.

`TemporalRuleEngine` should choose matching method based on condition shape:

- sustained frames
- sustained seconds
- sequence within frames
- sequence within seconds

`EventPolicyEngine` stays after temporal detection.

