# Review Episode / Low TTC Worker Tasks

## Status

Pending worker implementation.

## Task 1: AST and Parser

- [ ] Add `ReviewEpisodePolicy` dataclass.
- [ ] Extend `EventPolicy` with `episode`.
- [ ] Parse `emit.policy.episode.by`.
- [ ] Parse `emit.policy.episode.mode`.
- [ ] Support only `by: subject` and `mode: interval`.
- [ ] Reject unknown episode keys/values.
- [ ] Reject episode policy unless `emit.intent == "review"`.
- [ ] Keep existing `compact` rejection on review intent.

## Task 2: Episode Policy Engine

- [ ] Apply episode grouping after cooldown and debug/supporting compaction.
- [ ] Group only events whose rule has `emit.policy.episode`.
- [ ] Group by scenario/source/tag/rule/subject type/subject id.
- [ ] Split groups on frame gaps.
- [ ] Preserve first event top-level fields.
- [ ] Add `metadata.episode`.
- [ ] Merge temporal supporting frames across the episode.
- [ ] Preserve first event metadata keys.
- [ ] Keep `EngineStats.events_emitted` equal to final output count.

## Task 3: Classic Low TTC Rules

- [ ] Change `low_ttc_pair` intent from `review` to `supporting`.
- [ ] Keep `persistent_low_ttc_pair` as `review`.
- [ ] Add episode policy to `persistent_low_ttc_pair`.
- [ ] Verify `low_ttc_pair` remains available for temporal rules and viewer
  supporting context.

## Task 4: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_review_episode_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_classic_scenario_pack_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Real-data check:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00001-of-00150 -o review_payload_00001.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe -c "import json,collections; p=json.load(open('review_payload_00001.json',encoding='utf-8')); events=p['events']; review=p.get('review_event_indices',[]); print('events',len(events)); print('review',len(review)); print('review_tags',dict(collections.Counter(events[i]['tag_name'] for i in review))); print('episodes',sum(1 for e in events if 'episode' in e.get('metadata',{})));"
```

Expected behavior for the `00001` sample:

- `low_ttc_pair` should not appear in `review_tags`.
- `persistent_low_ttc_pair` should appear as fewer episode-level review events.
- The long `1217:1207` run should become one review episode instead of many
  sliding-window review events.
