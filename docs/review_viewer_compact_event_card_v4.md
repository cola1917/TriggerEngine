# Review Viewer Compact Event Card v4

## Goal

Turn the static viewer from a large debugging canvas into a compact event review
card. The user should open one local HTML file and immediately understand the
selected event without scanning a giant map or raw JSON.

This phase is visual-product cleanup only. It should not change engine output,
rule semantics, event grouping, payload export, or real-data execution.

## Current Problem

The current viewer is functionally useful but visually poor:

- the canvas still expands to fill the main page area
- the page feels like a debug console
- selected event details are shown as raw JSON
- map lines and non-subject agents compete with the event
- EGO/TARGET exists but is not presented as a review summary

The previous work made the data contract right. This version makes the first
screen readable.

## Target Experience

The first viewport should be a single compact review workspace:

- a centered event card
- a small BEV canvas, fixed visual size
- a concise event summary panel
- a short event list underneath or beside the canvas
- no raw JSON shown by default

The reviewer should be able to answer in a few seconds:

- What tag fired?
- Which scenario and frame/time?
- Who is EGO?
- Who is TARGET?
- Which way are they heading?
- What happened over the supporting frames?

## Layout Contract

Use a compact shell instead of a full-screen monitor layout.

Required structure:

- `.review-shell`
  - centered page container
  - max width around `1100px`
  - not full viewport height locked
- `.event-card`
  - the main framed review unit
  - contains canvas and event summary
  - border radius no more than `8px`
- `.scene-panel`
  - contains the BEV canvas
- `.summary-panel`
  - contains human-readable event facts
- `.event-list`
  - compact list of review events

Canvas requirements:

- canvas intrinsic size: `720x420`
- canvas CSS width: fixed or max-constrained, not `width: 100%` with
  `height: 100%`
- no `min-height: 520px`
- no full-screen app grid that forces the scene to become huge

## Summary Panel Contract

Replace default raw JSON details with human-readable rows.

Required DOM ids/classes:

- `eventSummary`
- `summaryTag`
- `summaryScenario`
- `summaryFrame`
- `summaryTime`
- `summaryEgo`
- `summaryTarget`
- `summaryRule`

Behavior:

- for `agent_pair`, parse `subject_id` as `ego:target`
- show EGO and TARGET as visible values in the summary
- for single-agent events, show the subject under EGO and show TARGET as `n/a`
- keep raw JSON optional behind a collapsed `<details id="rawEventDetails">`

## Visual Priority

The BEV should draw the event, not the world.

Required visual behavior:

- selected EGO and TARGET are the strongest colors
- non-subject agents are low opacity
- map features are low contrast and clipped to event-local bounds
- trajectories are visible but thinner than current agent boxes
- selected subject labels use `EGO` and `TARGET`
- heading arrows remain visible
- scale bar remains visible

The implementation can keep the existing canvas drawing helpers, but should
reduce visual noise and make selected subjects visually dominant.

## Non-Goals

- Do not build a frontend framework.
- Do not add a server.
- Do not add runtime controls for data export.
- Do not change rule definitions or engine output.
- Do not remove review events.
- Do not remove the raw event data entirely; only hide it by default.

## Acceptance

Pass the viewer contract tests and regenerate real-data output:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_review_viewer_v2_contract -v
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00000-of-00150 -o review_payload.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe tools\render_viewer.py review_payload.json -o viewer.html
```

Manual acceptance:

- first screen feels like one compact event review card
- canvas is not huge
- selected pair event is readable without opening JSON
- EGO/TARGET are clear both in the scene and in the summary panel
