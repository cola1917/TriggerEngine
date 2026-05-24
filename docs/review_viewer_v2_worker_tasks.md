# Review Viewer v2 Worker Tasks

## Task 1: Playback Frames

- [ ] Extend payload export to include future playback frames.
- [ ] Add `playback.history_frame_count`.
- [ ] Add `playback.future_frame_count`.
- [ ] Add `playback.current_frame_index`.
- [ ] Keep existing `frames` field as the viewer playback frame list.

## Task 2: Event Review Groups

- [ ] Add `classify_event_group(event)`.
- [ ] Add `review_events` containing primary events.
- [ ] Add `event_groups.primary`, `event_groups.supporting`, and
  `event_groups.debug` as event indexes.
- [ ] Default viewer event list to primary/review events.

## Task 3: Bounds And Map Crop

- [ ] Add scenario bounds based on agent positions.
- [ ] Add event bounds keyed by event index.
- [ ] Crop map features by scenario/event bounds before applying hard limits.
- [ ] Do not let far-away map features dominate the default canvas scale.

## Task 4: Viewer UI

- [ ] Add event group selector.
- [ ] Add view mode selector: `fit event`, `fit scenario`, `fit map`.
- [ ] Use payload bounds for projection.
- [ ] Render sequence timeline for temporal events with `source_tags` and
  `supporting_frame_indices`.
- [ ] Fade or hide unknown traffic lights by default.

## Task 5: CLI

- [ ] Add `--future-frames` to `export_review_payload.py`.
- [ ] Add `--map-crop-margin-m`.
- [ ] Keep `render_viewer.py` frontend-only: it must read payload JSON and must
  not import engine/data runner dependencies beyond the renderer.

## Task 6: Verification

- [ ] `tests/test_review_viewer_v2_contract.py` passes.
- [ ] Existing `tests/test_export_viewer_contract.py` passes.
- [ ] Full unittest suite passes.
- [ ] Generate a real payload and confirm:
  - `frames > input_frames`
  - `review_events` is smaller than `events`
  - selected event bounds are much tighter than map bounds
  - final cut-in tags remain inspectable
