# Review Rule Output Optimization Plan

## Problem

The 100-file run surfaced two review-output issues:

```text
cut_in_confirmed: 1
cut_in_risk: 1
sdc_repeated_lane_change: 22
```

`cut_in_confirmed` and `cut_in_risk` can describe the same cut-in episode. When
risk is present, it should be the primary review event. `cut_in_confirmed`
should not duplicate it as another review row.

`sdc_repeated_lane_change` is currently emitted once per frame in matching
scenarios. In the 100-file run, two files each emitted 11 review events for the
same SDC. That should be one interval episode per subject.

## Goals

- Keep review output compact and human-reviewable.
- Preserve supporting/debug signals for explainability.
- Prefer higher-risk review labels over lower-risk labels in the same family.

## Part 1: Repeated Lane Change Episode

Update the classic `sdc_repeated_lane_change` rule to use review episode policy:

```yaml
emit:
  tag: sdc_repeated_lane_change
  intent: review
  policy:
    episode:
      by: subject
      mode: interval
```

Expected behavior:

- consecutive `sdc_repeated_lane_change` review events for the same SDC compact
  to one episode
- metadata contains `episode.raw_event_frame_indices`
- real-data `00079` and `00095` should each emit one review episode, not 11

## Part 2: Review Family Dominance

Add review dominance for events that share:

- scenario
- source
- subject_type
- subject_id
- `metadata.review_family`
- overlapping episode/raw/supporting frame interval

Keep the event with the highest `metadata.review_priority`.

Classic cut-in metadata:

```yaml
cut_in_confirmed:
  metadata:
    review_family: cut_in
    review_priority: 10

cut_in_risk:
  metadata:
    review_family: cut_in
    review_priority: 20
```

Expected behavior:

- If `cut_in_confirmed` and `cut_in_risk` overlap for the same SDC-target pair,
  keep only `cut_in_risk` in final events.
- If only `cut_in_confirmed` exists, keep it as review.
- If different subjects or non-overlapping windows, keep both.

## Ordering

Apply policies in this order:

1. cooldown
2. compact debug/supporting
3. episode review events
4. review dominance

Dominance should run after episode compaction so it can compare interval-level
events, not raw per-frame fragments.

## Acceptance

- Unit tests prove dominance suppresses lower-priority overlapping review events.
- Classic cut-in rules declare review family and priority.
- Repeated lane change rule declares episode policy.
- Full test suite passes.
- Real-data 100-file summary should reduce:
  - `sdc_repeated_lane_change` review events from 22 to 2
  - cut-in review events in `00035` from confirmed+risk to risk only
