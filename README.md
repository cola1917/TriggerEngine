# Trigger Engine

Trigger Engine is a lightweight rule-based mining pipeline for autonomous
driving scenario review. It scans Waymo Open Dataset interactive TFRecord
shards, evaluates configurable trigger rules over SDC and target trajectories,
and exports review summaries plus static HTML viewers for manual inspection.

## What It Mines

The current classic rule pack focuses on high-value review scenarios:

- Low-TTC vehicle interaction with same-lane or same-path gating
- Confirmed cut-in sequence
- Map-aware red-light crossing
- SDC hard braking with interaction and traffic-light subtypes
- VRU close interaction
- SDC blocked or unable to proceed
- Lane-change conflict

Intermediate tags are kept as supporting/debug signals, while final analyst
items use `intent: review` and review episode policies to reduce frame-level
noise.

## Architecture

```text
Waymo TFRecord
  -> data adapter
  -> AlignmentContext
  -> Rule YAML / OperatorRegistry / RuleRegistry
  -> TriggerEngine
  -> TagEvents
  -> review batch summary + payload JSON
  -> static HTML review viewer
```

Core modules:

- `trigger_engine/alignment/`: scenario-aligned frame context
- `trigger_engine/rules/`: YAML parser, AST, compiler, rule execution
- `trigger_engine/operators/`: kinematic, map, interaction, and review predicates
- `trigger_engine/engine/`: trigger orchestration, subject caching, event policy
- `trigger_engine/scenarios/classic.py`: the current classic rule pack
- `tools/run_review_batch.py`: batch scan, profiling, payload, and viewer workflow

## Run

Run the current regression suite:

```powershell
E:\code\TriggerEngine\.venv\Scripts\python.exe -m unittest discover -s tests
```

Run a profiled batch over the first 100 validation shards and generate the final
review viewer:

```powershell
$paths = Get-ChildItem data -Filter validation_interactive.tfrecord-* |
  Sort-Object Name |
  Select-Object -First 100 |
  ForEach-Object { $_.FullName }

E:\code\TriggerEngine\.venv\Scripts\python.exe tools\run_review_batch.py $paths `
  --workers 5 `
  --profile-rules `
  --output review_batch_v2_final_100.json `
  --payload-dir review_payload_v2_final_100 `
  --view-output view_v2_final_100.html `
  --viewer-dir review_viewers_v2_final_100
```

Open `view_v2_final_100.html` to inspect the mined review scenarios.

## Current 100-Shard Result

The final 100-shard validation run scanned `29023` scenarios and selected
`162` default review scenarios:

```text
cut_in_confirmed: 21
persistent_low_ttc_pair: 7
sdc_blocked_unable_to_proceed: 52
sdc_hard_braking: 42
vru_close_interaction: 73
```

Run summary:

- `review_batch_v2_final_100.json`
- `review_payload_v2_final_100/` with 285 payload JSON files
- `review_viewers_v2_final_100/` with 162 per-scenario viewer pages
- `view_v2_final_100.html` as the review index

Runtime for the 100 shards was `703.72s` wall time at `41.24` scenarios/s.
Per-rule profiling shows the remaining engine hot spots are red-light stop-line
checks and `low_ttc_pair`, while total wall time is dominated by TFRecord
adapter work.

## Performance Work

The engine includes several result-preserving optimizations:

- SDC-only pair candidate generation
- Cheap TTC and lane-conflict candidate gates before expensive map matching
- Current-frame lane-review evaluation with raw lateral-displacement gates
- Red-light geometry caches for stop-line direction and lane heading checks
- SDC hard-braking motion gate before pair candidate generation
- Per-rule profiling for candidate counts, pair scans, emitted events, and time

The recent first-five-shard benchmark kept review output unchanged while
reducing engine time from `82.07s` to `9.01s`.
