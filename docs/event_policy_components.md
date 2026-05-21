# Event Policy Components

## Package Layout

Add:

```text
trigger_engine/
  engine/
    event_policy.py
```

Existing files to update:

```text
trigger_engine/rules/ast.py
trigger_engine/rules/parser.py
trigger_engine/engine/trigger_engine.py
```

## Data Structures

### EventPolicy

```python
@dataclass(frozen=True)
class EventPolicy:
    cooldown_frames: int = 0
```

Validation:

- `cooldown_frames >= 0`

Do not add `sequence`, `window`, `within`, `sustained`, or semantic `hold` here.
Those are temporal rule concerns.

### RuleEmit

Extend `RuleEmit`:

```python
@dataclass(frozen=True)
class RuleEmit:
    tag_name: str
    value: bool | int | float | str = True
    metadata: dict[str, object] = field(default_factory=dict)
    policy: EventPolicy = field(default_factory=EventPolicy)
```

## YAML Parser

Parse optional `emit.policy`:

```yaml
emit:
  tag: vehicle_stopped
  policy:
    cooldown_frames: 5
```

Reject:

- non-dict `emit.policy`
- negative `cooldown_frames`
- unknown policy keys

## EventPolicyEngine

```python
class EventPolicyEngine:
    def apply(
        self,
        events: tuple[TagEvent, ...],
        rules: tuple[Rule, ...],
    ) -> tuple[TagEvent, ...]:
        ...
```

Behavior:

- preserve original ordering of emitted events
- if no policy is configured, return events unchanged
- for `cooldown_frames > 0`, suppress repeated events with the same event key
  while `event.frame_index <= suppressed_until_frame_index`
- create a new `TagEvent` when metadata must be enriched because `TagEvent` is
  frozen
- do not mutate original event metadata dicts

Event key:

```python
(
    event.scenario_id,
    event.tag_name,
    event.subject_type,
    event.subject_id,
)
```

Rule lookup:

```python
rule_id -> rule.emit.policy
```

## TriggerEngine Integration

`TriggerEngine.evaluate(...)` should:

1. build raw single-frame events
2. build temporal events from the raw single-frame timeline
3. concatenate raw events
4. apply `EventPolicyEngine`
5. set `EngineStats.events_emitted` to the final event count

Important: temporal rules must still consume the raw single-frame events. A
cooldown on an intermediate tag should not break downstream temporal detection.

## Persistence Contract

No `TagEvent` field changes are required. Replay should read:

- `frame_index`
- `timestamp_seconds`
- `metadata.policy.output_frame_index`
- `metadata.policy.output_timestamp_seconds`
- `metadata.policy.suppressed_until_frame_index`
