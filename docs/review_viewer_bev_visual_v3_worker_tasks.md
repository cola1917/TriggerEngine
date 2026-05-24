# Review Viewer BEV Visual v3 Worker Tasks

## Task 1: Event-Local Projection

- [ ] Add `eventFrameTransform(event)`.
- [ ] Add `worldToEventLocal(point, transform)`.
- [ ] Center `fit event` on the selected subject or pair midpoint.
- [ ] Rotate event-local view by selected subject heading when available.
- [ ] Clamp zoom so vehicles are readable and the context window stays stable.

## Task 2: Map Visual Styling

- [ ] Replace raw lane centerline look with `drawLaneRibbon(feature)`.
- [ ] Keep lane/road lines muted and below agents.
- [ ] Hide map features outside the current local viewport.
- [ ] Draw stop/traffic light markers with a neutral unknown state.

## Task 3: Agent Visual Styling

- [ ] Add `drawHeadingArrow(agent)`.
- [ ] Make selected agents visually dominant.
- [ ] Make background agents low contrast.
- [ ] Keep labels small and avoid covering boxes.

## Task 4: Motion Context

- [ ] Add `drawAgentTrajectory(trackId)` for selected subject ids.
- [ ] Use history frames as a solid trail.
- [ ] Use future frames as a lighter/dashed trail.
- [ ] Highlight supporting frames from temporal metadata.

## Task 5: Review Overlays

- [ ] Add `drawEgoReticle()`.
- [ ] Add `drawScaleBar()`.
- [ ] Keep selected event details and sequence timeline visible on load.

## Task 6: Verification

- [ ] `tests/test_review_viewer_v2_contract.py` passes.
- [ ] Full unittest suite passes.
- [ ] Regenerate `review_payload.json` and `viewer.html` from real data.
- [ ] Open the HTML and confirm the first screen is a readable BEV scene, not a wireframe pile.
