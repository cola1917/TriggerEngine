from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY = PROJECT_ROOT / "third_party"
DEFAULT_TFRECORD = PROJECT_ROOT / "data" / "validation_interactive.tfrecord-00000-of-00150"
DEFAULT_OUTPUT = PROJECT_ROOT / "viewer.html"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(THIRD_PARTY))


def point_to_dict(point) -> dict[str, float]:
    return {"x": point.x, "y": point.y, "z": point.z}


def event_to_dict(event) -> dict[str, object]:
    return asdict(event)


def agent_to_dict(agent) -> dict[str, object]:
    return {
        "track_id": agent.track_id,
        "track_index": agent.track_index,
        "object_type": agent.object_type,
        "valid": agent.valid,
        "x": agent.center.x,
        "y": agent.center.y,
        "z": agent.center.z,
        "heading": agent.heading,
        "length": agent.length,
        "width": agent.width,
        "height": agent.height,
        "velocity_x": agent.velocity_x,
        "velocity_y": agent.velocity_y,
    }


def traffic_light_to_dict(light) -> dict[str, object]:
    return {
        "lane_id": light.lane_id,
        "state": light.state,
        "stop_point": point_to_dict(light.stop_point) if light.stop_point else None,
    }


def frame_to_dict(aligned_frame) -> dict[str, object]:
    frame = aligned_frame.frame
    return {
        "frame_index": frame.step_index,
        "timestamp_seconds": frame.timestamp_seconds,
        "phase": frame.phase,
        "visibility": aligned_frame.visibility,
        "agents": [agent_to_dict(agent) for agent in frame.agent_states if agent.valid],
        "traffic_lights": [
            traffic_light_to_dict(light) for light in frame.traffic_lights
        ],
    }


def map_feature_to_dict(feature) -> dict[str, object]:
    return {
        "feature_id": feature.feature_id,
        "feature_type": feature.feature_type,
        "polyline": [point_to_dict(point) for point in feature.polyline],
        "polygon": [point_to_dict(point) for point in feature.polygon],
        "properties": feature.properties,
    }


def build_viewer_payload(context, result, map_feature_limit: int = 500) -> dict[str, object]:
    map_features = sorted(
        context.map_features.values(),
        key=lambda feature: feature.feature_id,
    )[:map_feature_limit]
    return {
        "scenario_id": context.scenario_id,
        "source": context.source,
        "plan_id": result.plan_id,
        "watermark": {
            "frame_index": context.watermark.step_index,
            "timestamp_seconds": context.watermark.timestamp_seconds,
        },
        "frames": [frame_to_dict(frame) for frame in context.input_frames],
        "events": [event_to_dict(event) for event in result.events],
        "map_features": [map_feature_to_dict(feature) for feature in map_features],
        "stats": asdict(result.stats),
        "diagnostics": [asdict(diagnostic) for diagnostic in result.diagnostics],
    }


def render_viewer_html(payload: dict[str, object]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TriggerEngine Viewer - {payload["scenario_id"]}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --line: #d8dde6;
      --text: #1f2937;
      --muted: #64748b;
      --accent: #0f766e;
      --warn: #b45309;
      --danger: #b91c1c;
      --blue: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 13px/1.4 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .app {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 360px;
      min-height: 100vh;
    }}
    .main {{
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      min-width: 0;
    }}
    header, .controls, .sidebar {{
      background: var(--panel);
      border-color: var(--line);
    }}
    header {{
      border-bottom: 1px solid var(--line);
      padding: 12px 16px;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
    }}
    h1 {{
      font-size: 16px;
      margin: 0;
      font-weight: 650;
    }}
    .meta {{
      color: var(--muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .canvas-wrap {{
      min-height: 0;
      padding: 12px;
    }}
    canvas {{
      width: 100%;
      height: 100%;
      min-height: 520px;
      background: #eef2f7;
      border: 1px solid var(--line);
      display: block;
    }}
    .controls {{
      border-top: 1px solid var(--line);
      padding: 10px 12px;
      display: grid;
      grid-template-columns: auto auto minmax(160px, 1fr) auto auto;
      gap: 10px;
      align-items: center;
    }}
    button, select, input {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 7px 9px;
      font: inherit;
    }}
    button {{
      cursor: pointer;
      min-width: 38px;
    }}
    input[type="range"] {{
      width: 100%;
    }}
    .sidebar {{
      border-left: 1px solid var(--line);
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr) auto;
      min-width: 0;
    }}
    .side-section {{
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }}
    .side-section h2 {{
      font-size: 13px;
      margin: 0 0 8px;
      font-weight: 650;
    }}
    .event-list {{
      overflow: auto;
    }}
    .event {{
      padding: 9px 12px;
      border-bottom: 1px solid var(--line);
      cursor: pointer;
    }}
    .event.active {{
      background: #e6fffb;
      border-left: 4px solid var(--accent);
      padding-left: 8px;
    }}
    .event-title {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-weight: 650;
    }}
    .event-sub {{
      color: var(--muted);
      margin-top: 3px;
    }}
    .legend {{
      display: grid;
      gap: 5px;
      color: var(--muted);
    }}
    .dot {{
      display: inline-block;
      width: 10px;
      height: 10px;
      margin-right: 6px;
      vertical-align: -1px;
      border-radius: 50%;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--muted);
    }}
    @media (max-width: 900px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-left: 0; border-top: 1px solid var(--line); }}
      canvas {{ min-height: 420px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <div class="main">
      <header>
        <div>
          <h1 id="title"></h1>
          <div class="meta" id="subtitle"></div>
        </div>
        <div class="meta" id="frameMeta"></div>
      </header>
      <div class="canvas-wrap">
        <canvas id="canvas" width="1200" height="760"></canvas>
      </div>
      <div class="controls">
        <button id="prevBtn" title="Previous frame">&lt;</button>
        <button id="playBtn" title="Play or pause">Play</button>
        <input id="frameSlider" type="range" min="0" max="0" value="0">
        <button id="nextBtn" title="Next frame">&gt;</button>
        <select id="tagSelect"></select>
      </div>
    </div>
    <aside class="sidebar">
      <div class="side-section">
        <h2>Events</h2>
        <div class="meta" id="eventCount"></div>
      </div>
      <div class="side-section legend">
        <div><span class="dot" style="background:#2563eb"></span>agent</div>
        <div><span class="dot" style="background:#0f766e"></span>selected subject</div>
        <div><span class="dot" style="background:#b91c1c"></span>traffic stop</div>
      </div>
      <div class="event-list" id="eventList"></div>
      <div class="side-section">
        <h2>Selected</h2>
        <pre id="details"></pre>
      </div>
    </aside>
  </div>
  <script id="payload" type="application/json">{payload_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('payload').textContent);
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const slider = document.getElementById('frameSlider');
    const playBtn = document.getElementById('playBtn');
    const tagSelect = document.getElementById('tagSelect');
    const eventList = document.getElementById('eventList');
    const details = document.getElementById('details');
    const frameMeta = document.getElementById('frameMeta');
    const eventCount = document.getElementById('eventCount');
    let frameIndex = 0;
    let selectedEventIndex = -1;
    let timer = null;

    document.getElementById('title').textContent = payload.scenario_id;
    document.getElementById('subtitle').textContent = `${{payload.source || ''}} | plan ${{payload.plan_id}}`;
    slider.max = String(Math.max(payload.frames.length - 1, 0));

    const tags = Array.from(new Set(payload.events.map(e => e.tag_name))).sort();
    tagSelect.innerHTML = '<option value="">All tags</option>' + tags.map(tag => `<option>${{tag}}</option>`).join('');

    function selectedEvent() {{
      return payload.events[selectedEventIndex] || null;
    }}

    function filteredEvents() {{
      const tag = tagSelect.value;
      return payload.events
        .map((event, index) => [event, index])
        .filter(([event]) => !tag || event.tag_name === tag);
    }}

    function subjectIds(event) {{
      if (!event) return new Set();
      if (event.subject_type === 'agent_pair' && typeof event.subject_id === 'string') {{
        return new Set(event.subject_id.split(':').map(Number));
      }}
      if (event.subject_type === 'agent') return new Set([Number(event.subject_id)]);
      return new Set();
    }}

    function supportingFrames(event) {{
      if (!event || !event.metadata) return new Set();
      const values = event.metadata.supporting_frame_indices || [];
      return new Set(values);
    }}

    function worldBounds() {{
      const xs = [];
      const ys = [];
      for (const frame of payload.frames) {{
        for (const agent of frame.agents) {{
          xs.push(agent.x); ys.push(agent.y);
        }}
      }}
      for (const feature of payload.map_features || []) {{
        for (const p of [...(feature.polyline || []), ...(feature.polygon || [])]) {{
          xs.push(p.x); ys.push(p.y);
        }}
      }}
      if (!xs.length) return {{minX:-50, maxX:50, minY:-50, maxY:50}};
      return {{
        minX: Math.min(...xs) - 12,
        maxX: Math.max(...xs) + 12,
        minY: Math.min(...ys) - 12,
        maxY: Math.max(...ys) + 12,
      }};
    }}
    const bounds = worldBounds();

    function project(x, y) {{
      const pad = 34;
      const width = canvas.width - pad * 2;
      const height = canvas.height - pad * 2;
      const sx = width / Math.max(bounds.maxX - bounds.minX, 1);
      const sy = height / Math.max(bounds.maxY - bounds.minY, 1);
      const s = Math.min(sx, sy);
      const ox = (canvas.width - (bounds.maxX - bounds.minX) * s) / 2;
      const oy = (canvas.height - (bounds.maxY - bounds.minY) * s) / 2;
      return {{
        x: ox + (x - bounds.minX) * s,
        y: canvas.height - (oy + (y - bounds.minY) * s),
        s,
      }};
    }}

    function drawMap() {{
      ctx.save();
      ctx.lineWidth = 1;
      for (const feature of payload.map_features || []) {{
        const points = feature.polyline?.length ? feature.polyline : feature.polygon;
        if (!points || points.length < 2) continue;
        ctx.beginPath();
        points.forEach((p, i) => {{
          const q = project(p.x, p.y);
          if (i === 0) ctx.moveTo(q.x, q.y); else ctx.lineTo(q.x, q.y);
        }});
        if (feature.polygon?.length) ctx.closePath();
        ctx.strokeStyle = feature.feature_type === 'lane' ? '#c5ccd8' : '#d5dbe5';
        ctx.stroke();
      }}
      ctx.restore();
    }}

    function drawAgent(agent, selected, supporting) {{
      const p = project(agent.x, agent.y);
      const scale = p.s;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(-agent.heading);
      ctx.fillStyle = selected ? '#0f766e' : supporting ? '#b45309' : '#2563eb';
      ctx.strokeStyle = selected ? '#064e3b' : '#1e3a8a';
      ctx.lineWidth = selected ? 2.5 : 1;
      const length = Math.max(agent.length * scale, 7);
      const width = Math.max(agent.width * scale, 4);
      ctx.globalAlpha = selected || supporting ? 0.95 : 0.72;
      ctx.beginPath();
      ctx.rect(-length / 2, -width / 2, length, width);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(length / 2, 0);
      ctx.lineTo(length / 2 - 6, -3);
      ctx.lineTo(length / 2 - 6, 3);
      ctx.closePath();
      ctx.fillStyle = '#ffffff';
      ctx.fill();
      ctx.restore();

      ctx.fillStyle = selected ? '#064e3b' : '#334155';
      ctx.font = '11px system-ui';
      ctx.fillText(String(agent.track_id), p.x + 4, p.y - 4);
    }}

    function drawPairLine(frame, ids) {{
      if (ids.size !== 2) return;
      const agents = frame.agents.filter(agent => ids.has(agent.track_id));
      if (agents.length !== 2) return;
      const a = project(agents[0].x, agents[0].y);
      const b = project(agents[1].x, agents[1].y);
      ctx.save();
      ctx.strokeStyle = '#0f766e';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
      ctx.restore();
    }}

    function drawTraffic(frame) {{
      for (const light of frame.traffic_lights || []) {{
        if (!light.stop_point) continue;
        const p = project(light.stop_point.x, light.stop_point.y);
        ctx.fillStyle = light.state.includes('stop') ? '#b91c1c' : '#16a34a';
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
      }}
    }}

    function draw() {{
      const frame = payload.frames[frameIndex];
      const event = selectedEvent();
      const ids = subjectIds(event);
      const supports = supportingFrames(event);
      const isSupportingFrame = supports.has(frame.frame_index);

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      drawMap();
      drawTraffic(frame);
      drawPairLine(frame, ids);
      for (const agent of frame.agents) {{
        drawAgent(agent, ids.has(agent.track_id), isSupportingFrame);
      }}
      frameMeta.textContent = `frame ${{frame.frame_index}} / ${{payload.frames.length - 1}} | t=${{frame.timestamp_seconds.toFixed(2)}}s | events=${{payload.events.length}}`;
      slider.value = String(frameIndex);
    }}

    function renderEvents() {{
      const items = filteredEvents();
      eventCount.textContent = `${{items.length}} shown / ${{payload.events.length}} total`;
      eventList.innerHTML = items.map(([event, index]) => `
        <div class="event ${{index === selectedEventIndex ? 'active' : ''}}" data-index="${{index}}">
          <div class="event-title"><span>${{event.tag_name}}</span><span>f${{event.frame_index}}</span></div>
          <div class="event-sub">${{event.subject_type}} ${{event.subject_id ?? ''}} | ${{event.timestamp_seconds.toFixed(2)}}s</div>
        </div>
      `).join('');
      for (const node of eventList.querySelectorAll('.event')) {{
        node.addEventListener('click', () => {{
          selectedEventIndex = Number(node.dataset.index);
          frameIndex = payload.events[selectedEventIndex].frame_index;
          details.textContent = JSON.stringify(payload.events[selectedEventIndex], null, 2);
          renderEvents();
          draw();
        }});
      }}
    }}

    function step(delta) {{
      frameIndex = Math.max(0, Math.min(payload.frames.length - 1, frameIndex + delta));
      draw();
    }}

    document.getElementById('prevBtn').addEventListener('click', () => step(-1));
    document.getElementById('nextBtn').addEventListener('click', () => step(1));
    slider.addEventListener('input', () => {{ frameIndex = Number(slider.value); draw(); }});
    tagSelect.addEventListener('change', () => {{ selectedEventIndex = -1; details.textContent = ''; renderEvents(); draw(); }});
    playBtn.addEventListener('click', () => {{
      if (timer) {{
        clearInterval(timer);
        timer = null;
        playBtn.textContent = 'Play';
      }} else {{
        timer = setInterval(() => {{
          frameIndex = (frameIndex + 1) % payload.frames.length;
          draw();
        }}, 260);
        playBtn.textContent = 'Pause';
      }}
    }});

    renderEvents();
    draw();
  </script>
</body>
</html>
"""


def load_scenario(path: Path, scenario_index: int, scenario_id: str | None):
    from trigger_engine.data.readers import TFRecordScenarioReader

    reader = TFRecordScenarioReader()
    for index, scenario in enumerate(reader.iter_scenarios(path)):
        if scenario_id is not None and scenario.scenario_id == scenario_id:
            return scenario
        if scenario_id is None and index == scenario_index:
            return scenario
    if scenario_id is not None:
        raise ValueError(f"Scenario id '{scenario_id}' was not found in {path}")
    raise ValueError(f"Scenario index {scenario_index} was not found in {path}")


def build_context_and_result(path: Path, scenario_index: int, scenario_id: str | None):
    from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
    from trigger_engine.data.adapters import WaymoScenarioAdapter
    from trigger_engine.engine.registry import RuleRegistry
    from trigger_engine.engine.trigger_engine import TriggerEngine
    from trigger_engine.operators.builtins import register_builtin_operators
    from trigger_engine.operators.registry import OperatorRegistry
    from trigger_engine.scenarios.classic import register_classic_scenario_pack

    scenario = load_scenario(path, scenario_index, scenario_id)
    bundle = WaymoScenarioAdapter().from_proto(scenario, source=str(path))
    context = ScenarioAlignment().align(bundle)
    operators = OperatorRegistry()
    register_builtin_operators(operators)
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    result = TriggerEngine(operators, rules).evaluate(context)
    return context, result


def export_viewer(
    path: Path,
    output: Path,
    scenario_index: int = 0,
    scenario_id: str | None = None,
    map_feature_limit: int = 500,
) -> Path:
    context, result = build_context_and_result(path, scenario_index, scenario_id)
    payload = build_viewer_payload(context, result, map_feature_limit=map_feature_limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_viewer_html(payload), encoding="utf-8")
    return output


def export_review_payload(
    path: Path,
    output: Path,
    scenario_index: int = 0,
    scenario_id: str | None = None,
    map_feature_limit: int = 500,
) -> Path:
    context, result = build_context_and_result(path, scenario_index, scenario_id)
    payload = build_viewer_payload(context, result, map_feature_limit=map_feature_limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def render_viewer_from_payload(payload_path: Path, output: Path) -> Path:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_viewer_html(payload), encoding="utf-8")
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export a static TriggerEngine scenario viewer.")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_TFRECORD), help="Waymo TFRecord file")
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT), help="Output HTML path")
    parser.add_argument("--scenario-index", type=int, default=0, help="Scenario index in the shard")
    parser.add_argument("--scenario-id", default=None, help="Scenario id to export")
    parser.add_argument("--map-feature-limit", type=int, default=500, help="Maximum map features to embed")
    args = parser.parse_args(argv)

    export_viewer(
        Path(args.path),
        Path(args.output),
        scenario_index=args.scenario_index,
        scenario_id=args.scenario_id,
        map_feature_limit=args.map_feature_limit,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
