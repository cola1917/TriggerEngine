# Classic SDC-Only Rule Pack Plan

## Problem

After SDC-centric review migration, classic rules still contain generic
`agent` / `agent_pair` debug rules:

- `vehicle_stopped`
- `vehicle_stopped_for_3_frames`
- `cut_in_candidate`
- `cut_in_developing`
- `vehicle_stopped_at_red`
- `vehicle_still_stopped_at_red`

The product direction is now stricter: every classic rule should be from the
ego vehicle perspective. Generic scene-mining rules can live in a separate
future pack, but the default classic pack should not emit whole-scene agent or
pair signals.

## Decision

Make `CLASSIC_SCENARIO_RULES_YAML` SDC-only:

- single-agent rules use `sdc_agent`
- pair rules use `sdc_pair`
- no classic rule uses generic `agent` or `agent_pair`

## Rule Renaming

Rename generic stopped rules to make the SDC semantics explicit:

- `vehicle_stopped` -> `sdc_vehicle_stopped`
- `vehicle_stopped_for_3_frames` -> `sdc_vehicle_stopped_for_3_frames`
- `vehicle_stopped_at_red` -> `sdc_vehicle_stopped_at_red`
- `vehicle_still_stopped_at_red` -> `sdc_vehicle_still_stopped_at_red`

The emitted tag names should follow the same SDC-specific names. This prevents
downstream payloads from looking like generic scene tags.

## Cut-In Rules

Convert the remaining generic cut-in debug rules:

- `cut_in_candidate`: `agent_pair` -> `sdc_pair`
- `cut_in_developing`: `agent_pair` -> `sdc_pair`

Existing SDC cut-in sequence rules stay on `sdc_pair`.

Add review episode policy to:

- `cut_in_confirmed`
- `cut_in_risk`

This prevents repeated review rows when the same SDC cut-in episode remains true
across adjacent frames.

## Low TTC Rule Tightening

Keep:

- `low_ttc_pair`: `sdc_pair`, `intent: supporting`
- `persistent_low_ttc_pair`: `sdc_pair`, `intent: review`, `episode`

Tighten `predicate.pair_in_front.min_longitudinal_m` from `0.0` to at least
`1.0`. This avoids near-zero longitudinal overlap being treated as a front TTC
candidate.

## Red-Light Rules

Use SDC-specific stopped-at-red debug rules and keep map-aware red-light review
rules on `sdc_agent`.

## Non-Goals

- Do not add a separate generic mining pack in this round.
- Do not split rear-end/oncoming/crossing TTC families yet.
- Do not change operator implementations unless tests reveal a direct need.
