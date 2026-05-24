# Review Viewer BEV Visual v3

## Problem

Viewer v2 can select and crop an event, but the canvas still reads like a
debug wireframe. A usable review viewer should look like a compact top-down
scenario view: event-centered, layered, with clear map context, agent motion,
and selected subjects that can be recognized immediately.

## Target Behavior

- Open on the first review event.
- Use an event-local coordinate frame by default.
- Keep the selected event subject centered and readable.
- Draw map context as styled BEV layers, not thin undifferentiated lines.
- Draw agent boxes with heading arrows.
- Draw history/future trails for selected subjects.
- Draw background agents quietly.
- Include a scale bar and a center/event reticle.

## Required Rendering Pieces

The static HTML renderer should include these named functions so the visual
contract is explicit:

- `eventFrameTransform(event)`
- `worldToEventLocal(point, transform)`
- `drawLaneRibbon(feature)`
- `drawAgentTrajectory(trackId)`
- `drawHeadingArrow(agent)`
- `drawScaleBar()`
- `drawEgoReticle()`

## Coordinate Strategy

`fit event` should not be just a global x/y bbox. It should:

- choose the selected event's subject as the focal frame
- center the canvas on the selected agent or pair midpoint
- rotate the view so the focal heading points upward when available
- use a stable meter-per-pixel scale with min/max clamps
- keep a small context radius around the event, normally 30-60 meters

When heading is not available, fall back to world-aligned event bounds.

## Visual Layers

Draw in this order:

1. background
2. lane/road map features
3. traffic light/stop line markers
4. non-selected agents
5. selected subject trajectories
6. selected subject boxes and heading arrows
7. pair relation line
8. focal halo/reticle
9. scale bar and frame overlay

## Acceptance

The viewer is not accepted if opening a real scenario produces a dense
undifferentiated pile of grey lines. The first viewport must make the selected
event subject, its heading, and its short motion history visually obvious.
