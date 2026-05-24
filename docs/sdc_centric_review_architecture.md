# SDC-Centric Review Architecture

## Problem

The current review rules use generic `agent` and `agent_pair` subjects. For a
directed pair rule this means the engine can evaluate both:

- `A:B`
- `B:A`

That is useful for generic scene mining, but it is not the product semantics we
want for review. Review scenarios should be from the ego vehicle perspective:

- ego low TTC
- ego being cut in
- ego overtaking
- ego red-light behavior

## Design Decision

Add explicit SDC subjects:

- `sdc_agent`
- `sdc_pair`

`sdc_pair` always means:

```text
ego = SDC
target = another valid agent
subject_id = "{sdc_track_id}:{target_track_id}"
```

High-value review rules should use only `sdc_agent` or `sdc_pair`. Generic
`agent` / `agent_pair` rules may remain for supporting/debug mining, but they
should not be default review rules unless there is a very explicit reason.

## Alignment Contract

`ScenarioBundle` already carries `sdc_track_index`. Alignment should expose both:

- `AlignmentContext.sdc_track_index`
- `AlignmentContext.sdc_track_id`

`sdc_track_id` is resolved from the current frame agent whose
`track_index == bundle.sdc_track_index`.

If the current frame does not contain that agent, alignment should fail. Review
rules cannot be ego-centric without a stable ego identity.

## Rule YAML

```yaml
rules:
  - id: ego_low_ttc_pair
    subject: sdc_pair
    when:
      all:
        - operator: predicate.pair_types_are
          args:
            ego_type: vehicle
            other_type: vehicle
        - operator: predicate.pair_in_front
          args:
            min_longitudinal_m: 1.0
            max_lateral_m: 4.0
        - operator: predicate.low_ttc
          args:
            threshold_s: 3.0
            max_lateral_m: 4.0
    emit:
      tag: low_ttc_pair
      intent: supporting
```

Operators used by `sdc_pair` should be the same pair operators used by
`agent_pair`. The subject object is still an `AgentPairSubject`; only the rule
subject type and candidate generation differ.

For `sdc_agent`, existing agent operators should work against the SDC agent
state.

## Output Metadata

For `sdc_agent` events:

```python
metadata["ego_id"] = context.sdc_track_id
metadata["ego_role"] = "sdc"
```

For `sdc_pair` events:

```python
metadata["pair_mode"] = "sdc"
metadata["ego_id"] = context.sdc_track_id
metadata["ego_role"] = "sdc"
metadata["target_id"] = target.track_id
metadata["target_role"] = "interactive_agent"
```

Viewer can continue to split `subject_id` as `ego:target`, but now review pairs
are semantically guaranteed to be SDC first.

## Classic Rule Migration

Migrate high-value review paths to SDC subjects:

- low TTC source: `sdc_pair`
- persistent low TTC review episode: `sdc_pair`
- cut-in supporting sequence and final review: `sdc_pair`
- red-light approach/cross/run: `sdc_agent`

Rules that remain generic should be marked supporting/debug and should not enter
default review.

## Non-Goals

- Do not redesign TTC geometry in this round.
- Do not introduce oncoming/crossing TTC families yet.
- Do not remove `agent_pair`; it remains useful for generic mining and future
  non-ego scenario discovery.
