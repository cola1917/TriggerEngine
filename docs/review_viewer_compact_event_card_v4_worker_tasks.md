# Review Viewer Compact Event Card v4 Worker Tasks

## Objective

Refactor the static viewer HTML into a compact event review card. This is a
visual and interaction cleanup. Do not change engine semantics or payload
generation except where the viewer needs already-present payload fields.

## Failing Tests

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_review_viewer_v2_contract -v
```

Expected current failures:

- `test_fit_event_view_is_compact_and_role_readable`
- `test_compact_event_card_uses_summary_instead_of_default_raw_json`
- `test_summary_panel_derives_ego_and_target_from_selected_event`

## Implementation Tasks

- [ ] Replace the full-screen debug layout with compact card structure:
  - `.review-shell`
  - `.event-card`
  - `.scene-panel`
  - `.summary-panel`
  - `.event-list`
- [ ] Change canvas intrinsic size to `720x420`.
- [ ] Remove oversized canvas CSS:
  - no `height: 100%`
  - no `min-height: 520px`
  - avoid app layout that forces full viewport height
- [ ] Set shell max width around `1100px`.
- [ ] Keep existing playback controls, tag selector, event group selector, and
  prioritized review ordering.
- [ ] Replace default raw JSON selected panel with human-readable summary:
  - `eventSummary`
  - `summaryTag`
  - `summaryScenario`
  - `summaryFrame`
  - `summaryTime`
  - `summaryEgo`
  - `summaryTarget`
  - `summaryRule`
- [ ] Add `updateEventSummary(event)` and call it whenever selected event
  changes.
- [ ] For `agent_pair`, derive EGO/TARGET from `event.subject_id` split by `:`.
- [ ] For single-agent events, show subject as EGO and `n/a` as TARGET.
- [ ] Keep raw JSON only inside collapsed `<details id="rawEventDetails">`.
- [ ] Remove the default `<pre id="details"></pre>` selected panel.
- [ ] Preserve BEV helpers already added:
  - `eventFrameTransform`
  - `worldToEventLocal`
  - `drawLaneRibbon`
  - `drawAgentTrajectory`
  - `drawHeadingArrow`
  - `drawScaleBar`
  - `drawEgoReticle`
  - `roleForAgent`
  - `drawRoleBadge`
- [ ] Reduce visual noise if touching draw styles:
  - selected subjects strongest
  - non-subject agents lower opacity
  - map low contrast
  - trajectories thinner than current vehicle boxes

## Verification

After implementation:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_review_viewer_v2_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Then regenerate real viewer:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00000-of-00150 -o review_payload.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe tools\render_viewer.py review_payload.json -o viewer.html
```

## Acceptance Notes

The resulting page should feel like a compact event card, not a large map
dashboard. The reviewer should see the selected event summary and identify
EGO/TARGET without opening raw JSON.
