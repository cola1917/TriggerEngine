# Event Compaction / Pair Semantics Worker Tasks

## Status

Pending worker implementation.

## Task 1: AST and Parser

- [ ] Add `EventCompactionPolicy` dataclass.
- [ ] Extend `EventPolicy` with `compact`.
- [ ] Parse `emit.policy.compact.by`.
- [ ] Parse `emit.policy.compact.mode`.
- [ ] Support only `by: subject` and `mode: interval`.
- [ ] Reject unknown compact keys/values.
- [ ] Reject compact policy on `emit.intent: review`.
- [ ] Add pair semantics dataclass or field to `Rule`.
- [ ] Parse `pair.mode`.
- [ ] Default missing pair mode to `directed`.
- [ ] Reject `pair` on non-`agent_pair` rules.
- [ ] Reject unknown pair mode.

## Task 2: Pair Subject Generation

- [ ] Keep `directed` behavior backward compatible.
- [ ] For `unordered`, generate each pair only once.
- [ ] Use canonical subject id `min_id:max_id`.
- [ ] Ensure filtered subject construction also understands canonical unordered ids.
- [ ] Ensure candidate pruning and NumPy pair geometry preserve output correctness.
- [ ] Add metadata to emitted pair events:
  - directed: `pair_mode`, `ego_id`, `target_id`
  - unordered: `pair_mode`, `pair_member_ids`

## Task 3: Event Compaction

- [ ] Add final-output interval compaction after cooldown.
- [ ] Compact only rules with `emit.policy.compact`.
- [ ] Compact only debug/supporting intent events.
- [ ] Group by scenario/source/tag/rule/subject type/subject id.
- [ ] Split intervals on frame gaps.
- [ ] Preserve original first event fields for the output event.
- [ ] Add `metadata.compaction` with start/end frame, start/end timestamp,
  frame_count, raw_frame_indices, and raw_timestamps_seconds.
- [ ] Preserve existing metadata from the first event.
- [ ] Update `EngineStats.events_emitted` after compaction.
- [ ] Keep temporal rules based on raw single-frame events before compaction.

## Task 4: Classic Rules

- [ ] Mark symmetric supporting/debug pair rules as `pair.mode: unordered`.
- [ ] Add compact policy to noisy debug/supporting rules where useful.
- [ ] Keep high-value review rules uncompressed and directed unless explicitly
  symmetric.

Recommended first targets:

- `adjacent_vehicle`: unordered + compact
- `cut_in_lateral_approach`: directed, probably compact
- `same_path_overlap`: directed or unordered only after checking rule meaning
- `vehicle_stopped`: compact
- `vehicle_stopped_at_red`: compact

## Task 5: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_event_compaction_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_pair_semantics_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Real-data check:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00000-of-00150 -o review_payload.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe -c "import json,collections; p=json.load(open('review_payload.json',encoding='utf-8')); print('events',len(p['events'])); print('review',len(p.get('review_event_indices',[]))); print(collections.Counter(e.get('tag_name') for e in p['events'])); print(collections.Counter(e.get('metadata',{}).get('intent') for e in p['events']))"
```

Expected behavior:

- Review event count should not drop unexpectedly.
- Debug/supporting event count should drop for compacted rules.
- `vehicle_stopped` and similar events should appear as intervals.
- Temporal review rules such as `cut_in_confirmed` must still fire.
