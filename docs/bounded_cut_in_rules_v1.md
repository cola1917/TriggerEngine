# Bounded Cut-In Rules v1

This version tightens the default cut-in sequence rules without adding new DSL
syntax or engine parameters.

## Decision

`cut_in_lateral_approach` is no longer a global "any pair moving laterally
toward ego" tag. In the default classic pack it now means:

- both subjects are vehicles
- the other vehicle is in an adjacent-lane style spatial band
- the other vehicle is moving laterally toward ego

Rule shape:

```yaml
- id: cut_in_lateral_approach
  kind: single_frame
  subject: agent_pair
  when:
    all:
      - operator: predicate.pair_types_are
      - operator: predicate.lateral_gap_between
      - operator: predicate.lateral_motion_toward
```

## Why

The previous rule had no spatial boundary, so it generated many distant pair
tags and forced a full pair scan. That was too broad for a business cut-in tag.

The bounded rule keeps low-level operator purity:

- `predicate.lateral_motion_toward` remains pure motion logic
- business semantics are expressed by composing it with a spatial predicate
- candidate pruning stays automatic because `lateral_gap_between` has finite
  spatial bounds

## Output Impact

This intentionally reduces `cut_in_lateral_approach` volume. Far-away pairs that
only happen to move laterally are no longer emitted by the default classic pack.

Sequence tags still use:

```text
adjacent_vehicle -> cut_in_lateral_approach -> same_path_overlap
```

## Next Version

Sequence candidate gating remains a separate engine feature:

- use earlier sequence steps as subject candidates for later steps
- avoid evaluating later step tags globally when they are only used inside a
  temporal chain
- preserve standalone tag semantics when a tag is configured outside a gated
  sequence
