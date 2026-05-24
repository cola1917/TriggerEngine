# Review Episode / Low TTC Semantics Design

## Problem

Real-data file `validation_interactive.tfrecord-00001-of-00150` shows that
review output is still too fragmented:

- `low_ttc_pair` emits every matching frame.
- `persistent_low_ttc_pair` is a sustained temporal rule over `low_ttc_pair`.
- The sustained rule currently emits on every sliding window once the condition
  becomes true.

For one subject such as `1217:1207`, frames `0-10` produce 11 raw low-TTC
review events and 9 persistent low-TTC review events. This is one risk episode,
not 20 human-review items.

## Design Decision

Do not enable generic `compact` on review events. Review events need a separate
`episode` policy because the reviewer should see one semantic risk episode,
not a mechanically compressed row.

Use:

```yaml
emit:
  tag: persistent_low_ttc_pair
  intent: review
  policy:
    episode:
      by: subject
      mode: interval
```

MVP supports only:

- `episode.by: subject`
- `episode.mode: interval`

`episode` is allowed only on `emit.intent: review`.

## Output Contract

The output remains a `TagEvent`. The first event in the episode keeps its normal
top-level fields. The episode interval is stored in metadata:

```python
metadata["episode"] = {
    "mode": "interval",
    "by": "subject",
    "start_frame_index": 2,
    "end_frame_index": 10,
    "start_timestamp_seconds": 0.19998,
    "end_timestamp_seconds": 0.99981,
    "event_count": 9,
    "raw_event_frame_indices": (2, 3, 4, 5, 6, 7, 8, 9, 10),
    "raw_event_timestamps_seconds": (...),
    "supporting_frame_indices": (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    "supporting_timestamps_seconds": (...),
}
```

For temporal events, `supporting_frame_indices` should be the union of all
supporting frames across the merged review events. This lets replay cover the
whole underlying risk.

## Grouping Rules

Only merge consecutive review events with the same:

- `scenario_id`
- `source`
- `tag_name`
- `rule_id`
- `subject_type`
- `subject_id`

Split the episode when frame indices are not consecutive.

## Low TTC Rule Semantics

Change classic rule intent layering:

- `low_ttc_pair`: `intent: supporting`
- `persistent_low_ttc_pair`: `intent: review`

`low_ttc_pair` is a raw per-frame risk signal. It should support temporal
rules and viewer context, but it should not enter the default review list.

`persistent_low_ttc_pair` is the human-review event and should use episode
policy to emit one interval per continuous sustained risk.

## Direction Semantics Follow-up

The real-data sample also shows mutually reversed low-TTC pairs such as
`1207:1211` and `1211:1207`. This happens because the current low-TTC rule can
match oncoming/conflict geometry, not only rear-end following risk.

This round should not fully redesign TTC geometry. It should make the review
layer sane first:

- persistent low TTC review episodes are the default review item.
- raw low TTC pair hits are supporting signals.

A later rule pack can split rear-end TTC and oncoming TTC into separate review
families.
