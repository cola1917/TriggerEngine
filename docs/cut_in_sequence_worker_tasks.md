# Cut-in Sequence Worker Tasks

This document is the implementation checklist for the worker. The engine already
supports temporal `sequence`; this task only upgrades the classic cut-in rules
and the small operator surface needed by those rules.

## Goal

Replace the current sustained-only cut-in signal with a sequence-based signal:

```text
adjacent / different-path vehicle
  -> lateral motion toward ego path
  -> same-path overlap
  -> low TTC risk
```

The engine input remains `AlignmentContext`. Rule YAML is registered once through
`RuleRegistry`; runtime evaluation does not receive YAML.

## Semantics

`cut_in_confirmed` should mean the same ordered `agent_pair` first appeared near
ego in an adjacent lateral band, then moved laterally toward ego's path, then
appeared in ego's path/front corridor within a short frame window.

`cut_in_risk` should mean the same ordered `agent_pair` satisfied the same
sequence and also triggered `low_ttc_pair` within the same sequence window.

Do not implement ego braking in this task. Braking needs either pair-to-agent
subject mapping or a pair-level ego deceleration operator with history access;
that should be designed separately.

## Required Rule Tags

Single-frame `agent_pair` tags:

- [x] `adjacent_vehicle`
- [x] `cut_in_lateral_approach`
- [x] `same_path_overlap`
- [x] existing `low_ttc_pair`

Temporal `agent_pair` tags:

- [x] `cut_in_confirmed`
- [x] `cut_in_risk`

## Required Operators

Add these built-in predicates unless an equivalent implementation already
exists and the tests are adjusted to the existing name:

- [x] `predicate.lateral_gap_between`
  - subject: `agent_pair`
  - args: `min_lateral_m`, `max_lateral_m`, `max_longitudinal_m`
  - true when both agents are valid, absolute lateral distance in ego frame is
    inside `[min_lateral_m, max_lateral_m]`, and absolute longitudinal distance
    is within `max_longitudinal_m`.

- [x] `predicate.same_path_overlap`
  - subject: `agent_pair`
  - args: `max_lateral_m`, `min_longitudinal_m`, `max_longitudinal_m`
  - true when both agents are valid, other is in ego's forward corridor, lateral
    distance is small, and longitudinal distance is inside the configured range.

Reuse existing operators:

- [x] `predicate.pair_types_are`
- [x] `predicate.lateral_motion_toward`
- [x] `predicate.low_ttc`

## YAML Shape

The classic pack should contain rules equivalent to:

```yaml
- id: adjacent_vehicle
  kind: single_frame
  subject: agent_pair
  when:
    all:
      - operator: predicate.pair_types_are
        args:
          ego_type: vehicle
          other_type: vehicle
      - operator: predicate.lateral_gap_between
        args:
          min_lateral_m: 1.5
          max_lateral_m: 4.5
          max_longitudinal_m: 15.0
  emit:
    tag: adjacent_vehicle

- id: cut_in_lateral_approach
  kind: single_frame
  subject: agent_pair
  when:
    all:
      - operator: predicate.pair_types_are
        args:
          ego_type: vehicle
          other_type: vehicle
      - operator: predicate.lateral_motion_toward
        args:
          min_lateral_speed_mps: 0.2
  emit:
    tag: cut_in_lateral_approach

- id: same_path_overlap
  kind: single_frame
  subject: agent_pair
  when:
    all:
      - operator: predicate.pair_types_are
        args:
          ego_type: vehicle
          other_type: vehicle
      - operator: predicate.same_path_overlap
        args:
          max_lateral_m: 1.2
          min_longitudinal_m: 0.0
          max_longitudinal_m: 20.0
  emit:
    tag: same_path_overlap

- id: cut_in_confirmed
  kind: temporal
  subject: agent_pair
  when:
    sequence:
      - tag: adjacent_vehicle
      - tag: cut_in_lateral_approach
      - tag: same_path_overlap
    within_frames: 8
  emit:
    tag: cut_in_confirmed

- id: cut_in_risk
  kind: temporal
  subject: agent_pair
  when:
    sequence:
      - tag: adjacent_vehicle
      - tag: cut_in_lateral_approach
      - tag: same_path_overlap
      - tag: low_ttc_pair
    within_frames: 8
  emit:
    tag: cut_in_risk
```

Important: `cut_in_risk` must reference only single-frame source tags because the
current temporal engine builds its timeline from single-frame events.

## Acceptance

- [x] New operator contract tests pass.
- [x] Classic pack contract tests pass.
- [x] Classic e2e cut-in sequence test passes.
- [x] Full test suite passes:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='E:\code\TriggerEngine\.venv\Lib\site-packages'
C:\Users\test6\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```
