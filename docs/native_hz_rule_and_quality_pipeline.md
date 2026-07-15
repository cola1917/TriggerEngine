# Native-Hz Rules and Trajectory Quality Pipeline

## Decision

TriggerEngine should keep each data source on its native timeline. The default
pipeline does not resample, interpolate, smooth, or run Kalman filters. Rules
should express temporal semantics in seconds so Waymo 10Hz and nuScenes native
keyframes can use the same rule pack without pretending low-frequency
annotations contain high-frequency evidence.

## Rule Migration

The built-in classic rule pack uses seconds for temporal trigger semantics:

- `sustained.seconds` instead of `sustained.frames`
- `within_seconds` instead of `within_frames`
- operator arguments such as `min_stopped_duration_seconds` and
  `min_stable_duration_seconds` instead of frame counts

Frame-based fields remain temporarily accepted for external compatibility, but
the parser records deprecation diagnostics for:

- `when.sustained.frames`
- `when.within_frames`
- `when.all[*].for_last_n_frames`

`cooldown_frames` and `max_gap_frames` are intentionally not part of this
migration yet. They are discrete output or matching controls rather than primary
event-duration semantics.

## Quality Pipeline

The first trajectory pipeline stage is an annotator:

```text
ScenarioBundle(native timeline)
  -> TrajectoryQualityAnnotator
       - jump / implied speed checks
       - implied acceleration checks
       - heading jump checks
       - attach quality issues to ScenarioBundle
  -> ScenarioAlignment
  -> RuleEngine
```

The annotator must be non-destructive:

- Do not drop frames.
- Do not rewrite positions, velocities, headings, or validity.
- Do not interpolate missing data.
- Do not smooth with Kalman or offline future-aware methods.

Rules and viewers can consume the quality issues for explanation or filtering,
but raw trajectory values remain inspectable.

## Removal Criteria

Frame-based rule compatibility can be removed only after:

1. Built-in rule packs no longer emit deprecation diagnostics.
2. Waymo and nuScenes native-Hz smoke tests pass with seconds-based rules.
3. External or downstream rule packs have had one deprecation cycle to migrate.
