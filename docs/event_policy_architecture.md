# Event Policy Architecture

## Purpose

`EventPolicyEngine` is an engine post-processing layer. It does not decide
whether a rule is true. It decides how raw `TagEvent`s become stable final events
for persistence, metrics, and replay.

Current pipeline:

```text
AlignmentContext
  -> RuleEngine / TemporalRuleEngine
  -> raw TagEvent
  -> EventPolicyEngine
  -> final TagEvent
  -> persistence / replay
```

## Why It Exists

Some tags are naturally noisy:

- frame-level predicates can flicker for one frame
- long events can emit one event per frame
- intermediate tags such as `cut_in_lateral_approach` can be useful for rule
  composition but too noisy for persistence

`EventPolicyEngine` gives us a single place for:

- `cooldown`: suppress repeated final events for the same tag/subject
- `dedupe`: collapse identical final events when needed
- replay metadata for suppressed output windows

## MVP Scope

Implement only `cooldown_frames` first.

Explicit non-goals for this module:

- `sequence`
- `window`
- `within_frames` / `within_seconds`
- `sustained`
- semantic `hold`

Those belong to temporal rule evaluation because they decide whether an event is
true. Event policy only decides whether an already-true event should be emitted
again.

## Policy Location

Policy belongs to rule output configuration, not operator configuration:

```yaml
emit:
  tag: cut_in_lateral_approach
  policy:
    cooldown_frames: 10
```

Reasoning:

- operator remains pure computation
- rule remains the business semantic layer
- event policy remains output stabilization

## Time Semantics

`TagEvent.frame_index` and `TagEvent.timestamp_seconds` always represent the
final event output time.

For cooldown MVP:

- the first raw event in a cooldown window is emitted
- later raw events with the same key are suppressed
- emitted event keeps the first raw event's frame/timestamp
- metadata records the suppression window

Policy metadata shape:

```python
{
    "policy": {
        "cooldown_frames": 10,
        "output_frame_index": 20,
        "output_timestamp_seconds": 2.0,
        "suppressed_until_frame_index": 30,
    }
}
```

The policy layer does not invent `suppressed_until_timestamp_seconds`, because it
does not own the full scenario frame timeline. Replay can resolve the
suppressed-until frame back to a timestamp through the scenario frames.

The event identity key is:

```text
scenario_id + tag_name + subject_type + subject_id
```

`rule_id` is intentionally not part of the cooldown key. If two rules emit the
same tag for the same subject, they should stabilize as one final tag stream.

## Boundary With Temporal Rules

Business time semantics stay in the engine temporal layer:

```yaml
kind: temporal
when:
  sequence:
    - tag: overtake_start
    - tag: overtake_complete
  within_seconds: 5.0
```

This is not post-processing. It is the definition of the event.
