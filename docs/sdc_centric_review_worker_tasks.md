# SDC-Centric Review Worker Tasks

## Status

Pending worker implementation.

## Task 1: Alignment SDC Identity

- [ ] Add `sdc_track_index` and `sdc_track_id` to `AlignmentContext`.
- [ ] Resolve `sdc_track_id` from `current_frame.agent_states` by
  `track_index == bundle.sdc_track_index`.
- [ ] Reject alignment if the current frame does not contain the SDC track.
- [ ] Preserve existing alignment behavior and modality output.

## Task 2: Rule Parser and Subject Types

- [ ] Add `sdc_agent` and `sdc_pair` to valid rule subjects.
- [ ] Ensure `sdc_pair` works with existing pair operators.
- [ ] Ensure `sdc_agent` works with existing agent operators.
- [ ] Keep existing `agent` and `agent_pair` behavior unchanged.

## Task 3: RuleEngine / SubjectCache

- [ ] Generate exactly one `sdc_agent` subject per frame when SDC is valid.
- [ ] Generate `sdc_pair` subjects as SDC ego paired with every other valid
  agent in the frame.
- [ ] Never generate `target:sdc` for `sdc_pair`.
- [ ] Support `subject_id_filters` for `sdc_pair`.
- [ ] Support existing candidate pruning for `sdc_pair` when applicable.
- [ ] Add SDC metadata to `sdc_agent` and `sdc_pair` events.

## Task 4: Compiler / Registry Validation

- [ ] Allow operators with `subject_type == "agent"` to satisfy `sdc_agent`
  rules.
- [ ] Allow operators with `subject_type == "agent_pair"` to satisfy `sdc_pair`
  rules.
- [ ] Keep strict mismatch validation for unrelated subject types.

## Task 5: Classic Rule Migration

- [ ] Convert low TTC source and persistent review episode to `sdc_pair`.
- [ ] Convert cut-in source/sequence/review rules to `sdc_pair`.
- [ ] Convert red-light rules to `sdc_agent`.
- [ ] Keep review rules SDC-centric.
- [ ] Keep generic rules supporting/debug only if still needed.

## Task 6: Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sdc_subject_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_classic_sdc_review_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Real-data check:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00001-of-00150 -o review_payload_00001.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe -c "import json,collections; p=json.load(open('review_payload_00001.json',encoding='utf-8')); events=p['events']; review=p.get('review_event_indices',[]); print('review',len(review)); print('review_subjects',[events[i]['subject_id'] for i in review]); print('review_tags',dict(collections.Counter(events[i]['tag_name'] for i in review)));"
```

Expected behavior:

- Review event subject ids are always `sdc_id:target_id` for pair events.
- No review event uses `target_id:sdc_id`.
- Red-light review events use `subject_type == "sdc_agent"`.
