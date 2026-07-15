# Waymo Offline Profile

This note captures the first performance pass for the unified offline Waymo
runner. The goal is to keep output stable while removing avoidable overhead in
the 10 TFRecord shard path.

## Scope

- Source: `waymo`
- Input: `data/waymo/validation_interactive.tfrecord-00000-of-00150` through
  `data/waymo/validation_interactive.tfrecord-00009-of-00150`
- Batch size: 5
- Workers: 1
- Payload writing disabled for timing runs unless noted
- Scenario summaries disabled for compact summaries unless noted

## Baseline Findings

The original unified source path used `list_units()` and then `load_bundle()` for
each scenario. On Waymo this meant:

1. Scan each shard once to enumerate scenario units.
2. For every scenario unit, reopen and iterate from the beginning of the shard
   until the requested index.

That produced an accidental O(n^2) read pattern per shard and did not complete
the 10-shard run within a 600s timeout.

## Changes

- `WaymoOfflineSource.iter_bundles()` streams parsed scenarios once per shard.
- The unified runner prefers `iter_bundles()` when a source provides it.
- Batch size now groups streamed bundles without requiring prelisting.
- Scenario summaries can be omitted with `--no-scenario-summaries`.
- Payloads can be omitted with `--no-payloads`.
- Rule profile diagnostics are merged only at the run summary level and are not
  repeated inside every scenario summary.
- `SubjectCache` caches pair candidate plans by rule.
- Rule engine candidate counters use direct per-rule/per-frame lookups.
- Future-heading-change operator results are cached in the alignment context.
- Streaming sources can report `source_decode_seconds`,
  `source_adapter_seconds`, and `source_load_seconds`.
- Waymo adapter uses positional dataclass construction in hot loops.
- Waymo no-payload runs skip visual-only map feature conversion and keep the
  lane/stop-sign map features needed by rules. Payload-writing runs keep the
  full map for viewer output.
- `low_ttc_pair` now has an explicit `max_longitudinal_m` gate, and the
  candidate plan applies the low-TTC longitudinal, closing-speed, and TTC
  checks before lane/path matching.
- `lane_change_conflict` now skips pair generation when SDC lateral motion over
  the rule window is below `min_lateral_displacement_m`.

## Measured Runs

| Run | Command shape | Seconds | Engine seconds | Output check |
| --- | --- | ---: | ---: | --- |
| 10 shards before streaming | `--profile-rules --no-payloads` | timed out at 600s | n/a | incomplete |
| 10 shards after streaming | `--profile-rules --no-payloads` | 449s | 257s | 335 review events |
| 1 shard after subject cache | `--no-payloads --no-scenario-summaries` | 31.05s | 15.77s | 27 review events |
| 10 shards after subject cache | `--no-payloads --no-scenario-summaries` | 355.09s | 181.02s | 335 review events |
| 1 shard after heading cache | `--no-payloads --no-scenario-summaries` | 28.81s | 13.87s | 27 review events |
| 1 shard after heading cache, profiled | `--profile-rules --no-payloads --no-scenario-summaries` | 32.66s | 15.95s | 27 review events |
| 10 shards after heading cache | `--no-payloads --no-scenario-summaries` | 374.61s | 183.73s | 335 review events |
| 10 shards after heading cache, profiled | `--profile-rules --no-payloads --no-scenario-summaries` | 350.90s | 169.24s | 335 review events |
| 5 shards with source timing | `--profile-rules --no-payloads --no-scenario-summaries` | 152.65s | 76.78s | 171 review events |
| 5 shards after rule-map-only no-payload adapter | `--profile-rules --no-payloads --no-scenario-summaries` | 144.39s | 83.29s | 171 review events |
| 5 shards after pair gates | `--profile-rules --no-payloads --no-scenario-summaries` | 133.53s | 76.97s | 171 review events |

Single-run wall time has visible variance on this workstation. For the
10-shard path, the stable performance signal is that engine time sits around
169-184s after the current optimizations, while the total run remains dominated
by Waymo decode plus adapter/map conversion outside the engine timing bucket.

The 5-shard profile gives the current shorter feedback loop:

```text
total_scenarios: 1445
review_scenarios: 154
review_events: 171
source_decode_seconds: 2.97
source_adapter_seconds: 48.24
source_load_seconds: 51.21
quality_seconds: 5.81
engine_seconds: 83.29
postprocess_seconds: 0.04
```

Compared with the previous 5-shard source-timing run, adapter time dropped from
63.17s to 48.24s while review counts stayed unchanged.

After pair gates, the same 5-shard profile is:

```text
total_scenarios: 1445
review_scenarios: 154
review_events: 171
source_decode_seconds: 2.46
source_adapter_seconds: 44.99
source_load_seconds: 47.46
quality_seconds: 5.37
engine_seconds: 76.97
postprocess_seconds: 0.03
```

The review count again stayed unchanged. `low_ttc_pair` candidates dropped from
50,622 to 1,314. `lane_change_conflict` candidates dropped from 79,068 to
5,016, with pair scans limited to 82,071 for the 5-shard run.

The stable output count for the first shard is:

```text
cut_in_confirmed: 4
sdc_blocked_unable_to_proceed: 6
sdc_hard_braking: 1
sdc_repeated_lane_change: 10
vru_close_interaction: 6
```

The stable output count for the 10-shard run is:

```text
cut_in_confirmed: 141
lane_change_conflict: 8
red_light_running: 3
sdc_blocked_unable_to_proceed: 58
sdc_hard_braking: 8
sdc_repeated_lane_change: 87
vru_close_interaction: 30
```

The stable output count for the 5-shard run is:

```text
cut_in_confirmed: 67
lane_change_conflict: 3
red_light_running: 1
sdc_blocked_unable_to_proceed: 31
sdc_hard_braking: 2
sdc_repeated_lane_change: 47
vru_close_interaction: 20
```

## Current Hot Spots

The latest profiled 5-shard run shows the slowest rules:

| Rule | Seconds | Notes |
| --- | ---: | --- |
| `lane_change_conflict` | 16.08s | Pair rule, 82k pair scans |
| `sdc_repeated_lane_change` | 11.08s | Single-agent temporal rule |
| `red_light_stop_line_crossed` | 10.23s | SDC/map-light rule |
| `low_ttc_pair` | 9.86s | Pair rule, 1.3k candidates |
| `red_light_stop_line_approach` | 5.16s | SDC/map-light rule |

The non-rule profile also shows meaningful time in Waymo adapter conversion,
especially map point conversion and per-scenario lane index construction.

## Next Safe Optimizations

1. Cache SDC lane-change window features once per frame so
   `lane_change_conflict` and `sdc_repeated_lane_change` do not repeat lane
   matching over the same SDC history.
2. Reduce Waymo adapter map conversion cost by preserving raw numeric tuples
   until a map feature is actually needed by rules or viewer export.
3. Add red-light frame-level gating so red-light map operators skip frames with
   no red light stop state before lane geometry work.
4. Add worker parallelism at the shard or scenario-batch level after the
   single-worker output contract is fully stable.

## Verification

After the current changes:

```text
python -m unittest discover -s tests
Ran 301 tests: OK
```

The 5-shard and 10-shard output counts stayed unchanged across the comparable
profile runs.
