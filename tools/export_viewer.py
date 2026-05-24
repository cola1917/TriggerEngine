from __future__ import annotations

import argparse
import json
import os
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


_PRIMARY_TAGS = frozenset({
    "cut_in_confirmed",
    "cut_in_risk",
    "low_ttc_pair",
    "persistent_low_ttc_pair",
    "red_light_running",
})
_SUPPORTING_TAGS = frozenset({
    "adjacent_vehicle",
    "cut_in_lateral_approach",
    "same_path_overlap",
    "red_light_stop_line_approach",
    "red_light_stop_line_crossed",
})
_DEBUG_TAGS = frozenset({
    "vehicle_stopped",
    "vehicle_stopped_for_3_frames",
    "vehicle_stopped_at_red",
})


_INTENT_TO_GROUP = {
    "review": "primary",
    "supporting": "supporting",
    "debug": "debug",
}


def classify_event_group(event) -> str:
    metadata = event.metadata if hasattr(event, "metadata") else event.get("metadata", {})
    intent = metadata.get("intent") if isinstance(metadata, dict) else None
    if intent in _INTENT_TO_GROUP:
        return _INTENT_TO_GROUP[intent]
    tag = event.tag_name if hasattr(event, "tag_name") else event.get("tag_name", "")
    if tag in _PRIMARY_TAGS:
        return "primary"
    if tag in _SUPPORTING_TAGS:
        return "supporting"
    return "debug"


def _compute_agent_bounds(frames, margin: float) -> dict[str, float]:
    xs, ys = [], []
    for frame in frames:
        af = frame.frame if hasattr(frame, "frame") else frame
        for agent in af.agent_states if hasattr(af, "agent_states") else af.get("agents", []):
            if hasattr(agent, "valid") and not agent.valid:
                continue
            if isinstance(agent, dict) and not agent.get("valid", True):
                continue
            if hasattr(agent, "center"):
                xs.append(agent.center.x)
                ys.append(agent.center.y)
            elif isinstance(agent, dict):
                xs.append(agent.get("x", 0.0))
                ys.append(agent.get("y", 0.0))
    if not xs:
        return {"min_x": -50.0, "max_x": 50.0, "min_y": -50.0, "max_y": 50.0}
    return {
        "min_x": min(xs) - margin,
        "max_x": max(xs) + margin,
        "min_y": min(ys) - margin,
        "max_y": max(ys) + margin,
    }


def _feature_intersects_bounds(feature, bounds: dict[str, float]) -> bool:
    for point in list(feature.polyline) + list(feature.polygon):
        if bounds["min_x"] <= point.x <= bounds["max_x"] and bounds["min_y"] <= point.y <= bounds["max_y"]:
            return True
    return False


def _extract_subject_ids(event) -> set[str]:
    sid = event.subject_id if hasattr(event, "subject_id") else event.get("subject_id", "")
    stype = event.subject_type if hasattr(event, "subject_type") else event.get("subject_type", "")
    if stype == "agent_pair" and isinstance(sid, str):
        return set(sid.split(":"))
    return {str(sid)}


def _compute_event_bounds(event, all_frames, margin: float) -> dict[str, float] | None:
    subject_ids = _extract_subject_ids(event)
    if not subject_ids:
        return None
    xs, ys = [], []
    for frame in all_frames:
        af = frame.frame if hasattr(frame, "frame") else frame
        for agent in af.agent_states if hasattr(af, "agent_states") else af.get("agents", []):
            if hasattr(agent, "valid") and not agent.valid:
                continue
            if isinstance(agent, dict) and not agent.get("valid", True):
                continue
            aid = str(agent.track_id if hasattr(agent, "track_id") else agent.get("track_id", ""))
            if aid in subject_ids:
                if hasattr(agent, "center"):
                    xs.append(agent.center.x)
                    ys.append(agent.center.y)
                elif isinstance(agent, dict):
                    xs.append(agent.get("x", 0.0))
                    ys.append(agent.get("y", 0.0))
    if not xs:
        return None
    return {
        "min_x": min(xs) - margin,
        "max_x": max(xs) + margin,
        "min_y": min(ys) - margin,
        "max_y": max(ys) + margin,
    }


def build_viewer_payload(
    context,
    result,
    map_feature_limit: int = 500,
    playback_future_frames: int = 0,
    map_crop_margin_m: float = 0.0,
) -> dict[str, object]:
    # Playback frames
    input_frames = list(context.input_frames)
    future_frames = list(context.future_frames)[:playback_future_frames] if playback_future_frames > 0 else list(context.future_frames)
    all_playback_frames = input_frames + future_frames

    # Classify events
    events_list = list(result.events)
    review_event_indices = [i for i, e in enumerate(events_list) if classify_event_group(e) == "primary"]
    review_event_indices.sort(key=lambda i: 0 if (events_list[i].subject_type if hasattr(events_list[i], 'subject_type') else events_list[i].get('subject_type', '')) == 'agent_pair' else 1)
    review_events = [events_list[i] for i in review_event_indices]
    event_groups = {"primary": [], "supporting": [], "debug": []}
    for i, event in enumerate(events_list):
        event_groups[classify_event_group(event)].append(i)

    # Bounds
    scenario_bounds = _compute_agent_bounds(all_playback_frames, margin=12.0)
    event_bounds_by_event_index = {}
    for i, event in enumerate(events_list):
        eb = _compute_event_bounds(event, all_playback_frames, margin=12.0)
        if eb is not None:
            event_bounds_by_event_index[str(i)] = eb

    # Map features
    if map_crop_margin_m > 0:
        crop_bounds = _compute_agent_bounds(all_playback_frames, margin=map_crop_margin_m)
        map_features = sorted(
            [f for f in context.map_features.values() if _feature_intersects_bounds(f, crop_bounds)],
            key=lambda feature: feature.feature_id,
        )[:map_feature_limit]
    else:
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
        "playback": {
            "history_frame_count": len(input_frames),
            "future_frame_count": len(future_frames),
            "current_frame_index": context.watermark.step_index,
        },
        "frames": [frame_to_dict(frame) for frame in all_playback_frames],
        "events": [event_to_dict(event) for event in events_list],
        "review_events": [event_to_dict(event) for event in review_events],
        "review_event_indices": review_event_indices,
        "event_groups": event_groups,
        "map_features": [map_feature_to_dict(feature) for feature in map_features],
        "view": {
            "scenario_bounds": scenario_bounds,
            "event_bounds_by_event_index": event_bounds_by_event_index,
        },
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
    .review-shell {{
      max-width: 100vw;
      margin: 0 auto;
      padding: 12px;
    }}
    header {{
      padding: 8px 0;
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
    .event-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
    }}
    .scene-panel {{
      padding: 12px;
    }}
    canvas {{
      width: 100%;
      min-height: 520px;
      aspect-ratio: 16 / 9;
      height: auto;
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
      background: var(--panel);
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
    .summary-panel {{
      border-left: 1px solid var(--line);
      padding: 12px;
      font-size: 12px;
    }}
    .summary-panel h2 {{
      font-size: 13px;
      margin: 0 0 8px;
      font-weight: 650;
    }}
    .summary-row {{
      display: flex;
      justify-content: space-between;
      padding: 3px 0;
      border-bottom: 1px solid var(--line);
    }}
    .summary-label {{
      color: var(--muted);
      font-weight: 600;
    }}
    .summary-value {{
      text-align: right;
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .event-list {{
      margin-top: 12px;
      overflow: auto;
      max-height: 260px;
    }}
    .event {{
      padding: 9px 12px;
      border-bottom: 1px solid var(--line);
      cursor: pointer;
      background: var(--panel);
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
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--muted);
    }}
    @media (max-width: 900px) {{
      .event-card {{ grid-template-columns: 1fr; }}
      canvas {{ width: 100%; min-height: 360px; height: auto; }}
    }}
  </style>
</head>
<body>
  <div class="review-shell">
    <header>
      <div>
        <h1 id="title"></h1>
        <div class="meta" id="subtitle"></div>
      </div>
      <div class="meta" id="frameMeta"></div>
    </header>
    <div class="event-card">
      <div class="scene-panel">
        <canvas id="canvas" width="720" height="420"></canvas>
      </div>
      <div class="summary-panel" id="eventSummary">
        <h2>Event Summary</h2>
        <div class="summary-row"><span class="summary-label">Tag</span><span class="summary-value" id="summaryTag"></span></div>
        <div class="summary-row"><span class="summary-label">Scenario</span><span class="summary-value" id="summaryScenario"></span></div>
        <div class="summary-row"><span class="summary-label">Frame</span><span class="summary-value" id="summaryFrame"></span></div>
        <div class="summary-row"><span class="summary-label">Time</span><span class="summary-value" id="summaryTime"></span></div>
        <div class="summary-row"><span class="summary-label">EGO</span><span class="summary-value" id="summaryEgo"></span></div>
        <div class="summary-row"><span class="summary-label">TARGET</span><span class="summary-value" id="summaryTarget"></span></div>
        <div class="summary-row"><span class="summary-label">Rule</span><span class="summary-value" id="summaryRule"></span></div>
        <details id="rawEventDetails">
          <summary>Raw JSON</summary>
          <pre id="rawEventJson"></pre>
        </details>
      </div>
    </div>
    <div class="controls">
      <button id="prevBtn" title="Previous frame">&lt;</button>
      <button id="playBtn" title="Play or pause">Play</button>
      <input id="frameSlider" type="range" min="0" max="0" value="0">
      <button id="nextBtn" title="Next frame">&gt;</button>
      <select id="tagSelect"></select>
      <select id="eventGroupSelect">
        <option value="review">Review</option>
        <option value="primary">Primary</option>
        <option value="supporting">Supporting</option>
        <option value="debug">Debug</option>
        <option value="all">All</option>
      </select>
    </div>
    <div class="meta" id="eventCount"></div>
    <div class="event-list" id="eventList"></div>
    <div id="sequenceTimeline" style="display:none">
      <h2>Sequence Timeline</h2>
      <div id="timelineContent"></div>
    </div>
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
    const frameMeta = document.getElementById('frameMeta');
    const eventCount = document.getElementById('eventCount');
    const summaryTag = document.getElementById('summaryTag');
    const summaryScenario = document.getElementById('summaryScenario');
    const summaryFrame = document.getElementById('summaryFrame');
    const summaryTime = document.getElementById('summaryTime');
    const summaryEgo = document.getElementById('summaryEgo');
    const summaryTarget = document.getElementById('summaryTarget');
    const summaryRule = document.getElementById('summaryRule');
    const rawEventJson = document.getElementById('rawEventJson');
    let timer = null;

    document.getElementById('title').textContent = payload.scenario_id;
    document.getElementById('subtitle').textContent = `${{payload.source || ''}} | plan ${{payload.plan_id}}`;
    slider.max = String(Math.max(payload.frames.length - 1, 0));

    const tags = Array.from(new Set(payload.events.map(e => e.tag_name))).sort();
    tagSelect.innerHTML = '<option value="">All tags</option>' + tags.map(tag => `<option>${{tag}}</option>`).join('');

    // Event group selector
    const eventGroupSelect = document.getElementById('eventGroupSelect');
    const sequenceTimeline = document.getElementById('sequenceTimeline');
    let currentEventGroup = 'review';

    const egoColor = '#0f766e';
    const targetColor = '#b45309';

    function isPairEvent(event) {{
      return event && (event.subject_type === 'agent_pair' || event.subject_type === 'sdc_pair');
    }}

    function pairRoleIds(event) {{
      if (!isPairEvent(event) || typeof event.subject_id !== 'string') return null;
      const parts = event.subject_id.split(':');
      return {{egoId: Number(parts[0]), targetId: Number(parts[1])}};
    }}

    function egoIdForEvent(event) {{
      if (!event) return null;
      const ids = pairRoleIds(event);
      if (ids) return ids.egoId;
      const meta = event.metadata || {{}};
      if (Number.isFinite(Number(meta.ego_id))) return Number(meta.ego_id);
      if (event.subject_type === 'sdc_agent' || event.subject_type === 'agent') {{
        if (Number.isFinite(Number(event.subject_id))) return Number(event.subject_id);
      }}
      return null;
    }}

    function egoAgentForEvent(event, frame) {{
      const egoId = egoIdForEvent(event);
      if (egoId === null) return null;
      return (frame.agents || []).find(a => a.track_id === egoId) || null;
    }}

    function targetAgentForEvent(event, frame) {{
      const ids = pairRoleIds(event);
      if (!ids) return null;
      return (frame.agents || []).find(a => a.track_id === ids.targetId) || null;
    }}

    function roleForAgent(event, trackId) {{
      const ids = pairRoleIds(event);
      if (ids) {{
        if (trackId === ids.egoId) return 'EGO';
        if (trackId === ids.targetId) return 'TARGET';
      }}
      const egoId = egoIdForEvent(event);
      if (egoId !== null && trackId === egoId) return 'EGO';
      return null;
    }}

    function drawRoleLabel(agent, role) {{
      if (!role) return;
      const p = project(agent.x, agent.y);
      const color = role === 'EGO' ? egoColor : targetColor;
      ctx.save();
      ctx.font = 'bold 13px system-ui';
      const tw = ctx.measureText(role).width;
      const bx = p.x - tw / 2 - 8;
      const by = p.y - 34;
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.96;
      ctx.beginPath();
      ctx.roundRect(bx, by, tw + 16, 22, 5);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(role, p.x, by + 11);
      ctx.restore();
    }}

    function drawRoleBadge(agent, role) {{
      drawRoleLabel(agent, role);
    }}

    function firstReviewEventIndex() {{
      const indices = payload.review_event_indices || [];
      return indices.length > 0 ? indices[0] : 0;
    }}
    let selectedEventIndex = firstReviewEventIndex();
    let frameIndex = (payload.events[selectedEventIndex] || {{}}).frame_index || 0;

    function updateEventSummary(event) {{
      if (!event) {{
        summaryTag.textContent = '';
        summaryScenario.textContent = '';
        summaryFrame.textContent = '';
        summaryTime.textContent = '';
        summaryEgo.textContent = '';
        summaryTarget.textContent = '';
        summaryRule.textContent = '';
        rawEventJson.textContent = '';
        sequenceTimeline.style.display = 'none';
        return;
      }}
      summaryTag.textContent = event.tag_name || '';
      summaryScenario.textContent = event.scenario_id || '';
      summaryFrame.textContent = event.frame_index;
      summaryTime.textContent = (event.timestamp_seconds || 0).toFixed(2) + 's';
      summaryRule.textContent = event.rule_name || '';
      const ids = pairRoleIds(event);
      if (ids) {{
        summaryEgo.textContent = String(ids.egoId);
        summaryTarget.textContent = String(ids.targetId);
      }} else {{
        summaryEgo.textContent = String(event.subject_id ?? '');
        summaryTarget.textContent = 'n/a';
      }}
      rawEventJson.textContent = JSON.stringify(event, null, 2);
      updateSequenceTimeline();
    }}

    function updateSelectionDetails() {{
      updateEventSummary(selectedEvent());
    }}

    function getEventsForGroup(group) {{
      if (group === 'all') return payload.events.map((e, i) => [e, i]);
      if (group === 'review') return (payload.review_event_indices || []).map(i => [payload.events[i], i]);
      const groups = payload.event_groups || {{}};
      const indices = groups[group] || [];
      return indices.map(i => [payload.events[i], i]);
    }}

    function selectedEvent() {{
      return payload.events[selectedEventIndex] || null;
    }}

    function filteredEvents() {{
      const tag = tagSelect.value;
      let items = getEventsForGroup(currentEventGroup);
      if (tag) items = items.filter(([event]) => event.tag_name === tag);
      return items;
    }}

    function updateSequenceTimeline() {{
      const event = selectedEvent();
      if (!event || !event.metadata || !event.metadata.source_tags) {{
        sequenceTimeline.style.display = 'none';
        return;
      }}
      sequenceTimeline.style.display = '';
      const tags = event.metadata.source_tags || [];
      const frames = event.metadata.supporting_frame_indices || [];
      let html = '<div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">';
      for (let i = 0; i < tags.length; i++) {{
        const frameIdx = frames[i] !== undefined ? frames[i] : '?';
        html += `<span style="background:#e6fffb;border:1px solid #0f766e;border-radius:4px;padding:2px 6px;font-size:11px">${{tags[i]}}<br><small>f${{frameIdx}}</small></span>`;
        if (i < tags.length - 1) html += '<span style="color:#64748b">&rarr;</span>';
      }}
      html += '</div>';
      document.getElementById('timelineContent').innerHTML = html;
    }}

    function subjectIds(event) {{
      if (!event) return new Set();
      if (isPairEvent(event) && typeof event.subject_id === 'string') {{
        return new Set(event.subject_id.split(':').map(Number));
      }}
      const egoId = egoIdForEvent(event);
      if (egoId !== null) return new Set([egoId]);
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

    function getViewBounds() {{
      if (selectedEventIndex >= 0 && payload.view && payload.view.event_bounds_by_event_index) {{
        const b = payload.view.event_bounds_by_event_index[String(selectedEventIndex)];
        if (b) return {{minX: b.min_x, maxX: b.max_x, minY: b.min_y, maxY: b.max_y}};
      }}
      if (payload.view && payload.view.scenario_bounds) {{
        const b = payload.view.scenario_bounds;
        return {{minX: b.min_x, maxX: b.max_x, minY: b.min_y, maxY: b.max_y}};
      }}
      return worldBounds();
    }}
    let bounds = getViewBounds();
    let activeTransform = null;

    function viewWidth() {{
      return canvas.clientWidth || 720;
    }}

    function viewHeight() {{
      return canvas.clientHeight || 520;
    }}

    function resizeCanvasToDisplaySize() {{
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== width || canvas.height !== height) {{
        canvas.width = width;
        canvas.height = height;
      }}
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }}

    function project(x, y) {{
      const pad = 34;
      const cw = viewWidth();
      const ch = viewHeight();
      const width = cw - pad * 2;
      const height = ch - pad * 2;
      const transform = eventFrameTransform(selectedEvent());
      if (transform) {{
        activeTransform = transform;
        const local = worldToEventLocal({{x, y}}, transform);
        const radius = transform.radius || 40;
        const s = Math.min(width, height) / (radius * 2);
        const anchor = transform.anchor || {{x: 0.5, y: 0.5}};
        const ox = anchor.x * canvas.width;
        const oy = anchor.y * canvas.height;
        const screenOx = anchor.x * cw;
        const screenOy = anchor.y * ch;
        return {{
          x: screenOx + local.x * s,
          y: screenOy - local.y * s,
          s,
        }};
      }}
      activeTransform = null;
      const sx = width / Math.max(bounds.maxX - bounds.minX, 1);
      const sy = height / Math.max(bounds.maxY - bounds.minY, 1);
      const s = Math.min(sx, sy);
      const ox = (cw - (bounds.maxX - bounds.minX) * s) / 2;
      const oy = (ch - (bounds.maxY - bounds.minY) * s) / 2;
      return {{
        x: ox + (x - bounds.minX) * s,
        y: ch - (oy + (y - bounds.minY) * s),
        s,
      }};
    }}

    function featureIntersectsBounds(feature, b) {{
      if (activeTransform) {{
        const radius = activeTransform.radius || 40;
        const margin = 10;
        const localBounds = {{
          minX: -(radius + margin), maxX: radius + margin,
          minY: -(radius + margin), maxY: radius + margin,
        }};
        const points = [...(feature.polyline || []), ...(feature.polygon || [])];
        return points.some(p => {{
          const local = worldToEventLocal(p, activeTransform);
          return local.x >= localBounds.minX && local.x <= localBounds.maxX &&
                 local.y >= localBounds.minY && local.y <= localBounds.maxY;
        }});
      }}
      const points = [...(feature.polyline || []), ...(feature.polygon || [])];
      return points.some(p => p.x >= b.minX && p.x <= b.maxX && p.y >= b.minY && p.y <= b.maxY);
    }}

    function drawMap() {{
      ctx.save();
      ctx.lineWidth = 1;
      for (const feature of payload.map_features || []) {{
        if (!featureIntersectsBounds(feature, bounds)) continue;
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

    function drawFocalHalo(agent) {{
      const p = project(agent.x, agent.y);
      const r = Math.max(agent.length, agent.width) * p.s * 0.9;
      ctx.save();
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 6, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(15,118,110,0.12)';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2);
      ctx.strokeStyle = '#0f766e';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.restore();
    }}

    function drawAgent(agent, selected, supporting, role) {{
      const p = project(agent.x, agent.y);
      const scale = p.s;
      const headingOffset = activeTransform ? activeTransform.heading : 0;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(-(agent.heading - headingOffset));
      let fillColor = '#2563eb';
      let strokeColor = '#1e3a8a';
      if (role === 'EGO') {{ fillColor = egoColor; strokeColor = '#064e3b'; }}
      else if (role === 'TARGET') {{ fillColor = targetColor; strokeColor = '#92400e'; }}
      else if (supporting) {{ fillColor = '#b45309'; strokeColor = '#92400e'; }}
      ctx.fillStyle = fillColor;
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = role ? (role === 'EGO' ? 4 : 3) : (selected ? 2.5 : 1);
      const length = Math.max(agent.length * scale, 7);
      const width = Math.max(agent.width * scale, 4);
      ctx.globalAlpha = selected || supporting ? 1 : 0.45;
      if (role) {{
        ctx.shadowColor = role === 'EGO' ? 'rgba(15,118,110,0.42)' : 'rgba(180,83,9,0.42)';
        ctx.shadowBlur = 10;
      }}
      ctx.beginPath();
      ctx.rect(-length / 2, -width / 2, length, width);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(length / 2, 0);
      ctx.lineTo(length / 2 - 6, -3);
      ctx.lineTo(length / 2 - 6, 3);
      ctx.closePath();
      ctx.fillStyle = '#ffffff';
      ctx.fill();
      ctx.restore();

      ctx.fillStyle = role === 'TARGET' ? '#78350f' : selected ? '#064e3b' : '#334155';
      ctx.font = role ? 'bold 12px system-ui' : '11px system-ui';
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

    let renderQualityMode = 'high';

    function eventFrameTransform(event) {{
      if (!event) return null;
      const frame = payload.frames[frameIndex] || payload.frames[0];
      const ego = egoAgentForEvent(event, frame);
      if (ego) return {{cx: ego.x, cy: ego.y, heading: ego.heading, radius: 45, anchor: {{x: 0.5, y: 0.68}}}};
      const ids = subjectIds(event);
      if (ids.size === 0) return null;
      for (const agent of frame.agents) {{
        if (ids.has(agent.track_id)) {{
          return {{cx: agent.x, cy: agent.y, heading: agent.heading, radius: 40}};
        }}
      }}
      return null;
    }}

    function worldToEventLocal(point, transform) {{
      if (!transform) return point;
      const dx = point.x - transform.cx;
      const dy = point.y - transform.cy;
      const cos = Math.cos(-transform.heading);
      const sin = Math.sin(-transform.heading);
      return {{x: dx * cos - dy * sin, y: dx * sin + dy * cos}};
    }}

    function drawLaneRibbon(feature) {{
      const points = feature.polyline?.length ? feature.polyline : feature.polygon;
      if (!points || points.length < 2) return;
      ctx.save();
      ctx.beginPath();
      points.forEach((p, i) => {{
        const q = project(p.x, p.y);
        if (i === 0) ctx.moveTo(q.x, q.y); else ctx.lineTo(q.x, q.y);
      }});
      if (feature.polygon?.length) ctx.closePath();
      const isLane = feature.feature_type === 'lane';
      ctx.strokeStyle = isLane ? '#b8c2d0' : '#ccd3de';
      ctx.lineWidth = isLane ? 3 : 2;
      ctx.globalAlpha = 0.5;
      ctx.stroke();
      if (isLane && points.length >= 2) {{
        ctx.strokeStyle = '#d5dbe5';
        ctx.lineWidth = 1;
        ctx.setLineDash([6, 8]);
        ctx.stroke();
      }}
      ctx.restore();
    }}

    function drawAgentTrajectory(trackId) {{
      const id = Number(trackId);
      const supports = supportingFrames(selectedEvent());
      for (let fi = 0; fi < payload.frames.length; fi++) {{
        const f = payload.frames[fi];
        const agent = f.agents.find(a => a.track_id === id);
        if (!agent) continue;
        const isSupport = supports.has(f.frame_index);
        const isFuture = f.phase === 'future';
        const isPast = f.phase === 'history' || f.phase === 'current';
        if (fi === frameIndex) continue;
        const p = project(agent.x, agent.y);
        ctx.save();
        ctx.beginPath();
        ctx.arc(p.x, p.y, isSupport ? 3.5 : 2.5, 0, Math.PI * 2);
        if (isPast) {{
          ctx.fillStyle = isSupport ? 'rgba(180,83,9,0.6)' : 'rgba(15,118,110,0.35)';
        }} else {{
          ctx.fillStyle = isSupport ? 'rgba(180,83,9,0.3)' : 'rgba(15,118,110,0.15)';
          ctx.setLineDash([2, 2]);
        }}
        ctx.fill();
        ctx.restore();
      }}
      const sorted = payload.frames
        .map((f, i) => [f, i])
        .filter(([f]) => {{
          const a = f.agents.find(a => a.track_id === id);
          return a && (f.phase === 'history' || f.phase === 'current');
        }});
      if (sorted.length >= 2) {{
        ctx.save();
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(15,118,110,0.3)';
        ctx.lineWidth = 1.5;
        sorted.forEach(([f], idx) => {{
          const a = f.agents.find(a => a.track_id === id);
          const p = project(a.x, a.y);
          if (idx === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y);
        }});
        ctx.stroke();
        ctx.restore();
      }}
    }}

    function drawHeadingArrow(agent) {{
      const p = project(agent.x, agent.y);
      const scale = p.s;
      const headingOffset = activeTransform ? activeTransform.heading : 0;
      const len = Math.max(agent.length * scale * 0.7, 10);
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(-(agent.heading - headingOffset));
      ctx.beginPath();
      ctx.moveTo(len / 2 + 4, 0);
      ctx.lineTo(len / 2 - 5, -4);
      ctx.lineTo(len / 2 - 5, 4);
      ctx.closePath();
      ctx.fillStyle = '#ffffff';
      ctx.globalAlpha = 0.9;
      ctx.fill();
      ctx.restore();
    }}

    function drawScaleBar() {{
      let metersPerPixel;
      if (activeTransform) {{
        const pad = 34;
        const width = viewWidth() - pad * 2;
        const height = viewHeight() - pad * 2;
        const radius = activeTransform.radius || 40;
        const s = Math.min(width, height) / (radius * 2);
        metersPerPixel = 1 / s;
      }} else {{
        metersPerPixel = (bounds.maxX - bounds.minX) / Math.max(viewWidth() - 68, 1);
      }}
      const candidates = [1, 2, 5, 10, 20, 50, 100, 200, 500];
      let barMeters = candidates[candidates.length - 1];
      for (const c of candidates) {{
        if (c / metersPerPixel > 40 && c / metersPerPixel < 200) {{ barMeters = c; break; }}
      }}
      const barPx = barMeters / metersPerPixel;
      const x = viewWidth() - barPx - 20;
      const y = viewHeight() - 20;
      ctx.save();
      ctx.strokeStyle = '#64748b';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, y); ctx.lineTo(x + barPx, y);
      ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4);
      ctx.moveTo(x + barPx, y - 4); ctx.lineTo(x + barPx, y + 4);
      ctx.stroke();
      ctx.fillStyle = '#64748b';
      ctx.font = '10px system-ui';
      ctx.textAlign = 'center';
      ctx.fillText(barMeters + 'm', x + barPx / 2, y - 6);
      ctx.restore();
    }}

    function drawEgoReticle() {{
      const transform = activeTransform;
      const anchor = transform && transform.anchor ? transform.anchor : {{x: 0.5, y: 0.5}};
      const cx = anchor.x * viewWidth();
      const cy = anchor.y * viewHeight();
      const r = 8;
      ctx.save();
      ctx.strokeStyle = 'rgba(15,118,110,0.35)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(cx - r - 4, cy); ctx.lineTo(cx + r + 4, cy);
      ctx.moveTo(cx, cy - r - 4); ctx.lineTo(cx, cy + r + 4);
      ctx.stroke();
      ctx.restore();
    }}

    function drawEgoAnchor() {{
      const event = selectedEvent();
      const frame = payload.frames[frameIndex] || payload.frames[0];
      const ego = egoAgentForEvent(event, frame);
      if (!ego || !activeTransform) return;
      const p = project(ego.x, ego.y);
      ctx.save();
      ctx.strokeStyle = '#0f766e';
      ctx.fillStyle = 'rgba(15,118,110,0.08)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(p.x, p.y, 18, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(p.x - 24, p.y); ctx.lineTo(p.x + 24, p.y);
      ctx.moveTo(p.x, p.y - 24); ctx.lineTo(p.x, p.y + 24);
      ctx.stroke();
      ctx.restore();
    }}

    function draw() {{
      resizeCanvasToDisplaySize();
      bounds = getViewBounds();
      activeTransform = eventFrameTransform(selectedEvent());
      const frame = payload.frames[frameIndex];
      const event = selectedEvent();
      const ids = subjectIds(event);
      const supports = supportingFrames(event);
      const isSupportingFrame = supports.has(frame.frame_index);

      ctx.clearRect(0, 0, viewWidth(), viewHeight());
      // Layer 1-2: map
      for (const feature of payload.map_features || []) {{
        if (!featureIntersectsBounds(feature, bounds)) continue;
        drawLaneRibbon(feature);
      }}
      // Layer 3: traffic
      drawTraffic(frame);
      drawEgoAnchor();
      // Layer 4: non-selected agents (quiet)
      for (const agent of frame.agents) {{
        if (!ids.has(agent.track_id)) drawAgent(agent, false, false, null);
      }}
      // Layer 5: trajectories
      for (const id of ids) {{ drawAgentTrajectory(id); }}
      // Layer 6: selected agents
      for (const agent of frame.agents) {{
        if (ids.has(agent.track_id)) {{
          const role = roleForAgent(event, agent.track_id);
          drawFocalHalo(agent);
          drawAgent(agent, true, isSupportingFrame, role);
          drawHeadingArrow(agent);
          drawRoleLabel(agent, role);
        }}
      }}
      // Layer 7: pair line
      drawPairLine(frame, ids);
      // Layer 8-9: overlays
      drawEgoReticle();
      drawScaleBar();
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
          updateSelectionDetails();
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
    tagSelect.addEventListener('change', () => {{ selectedEventIndex = -1; updateSelectionDetails(); renderEvents(); draw(); }});
    eventGroupSelect.addEventListener('change', () => {{ currentEventGroup = eventGroupSelect.value; selectedEventIndex = -1; updateSelectionDetails(); renderEvents(); draw(); }});
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
    window.addEventListener('resize', () => {{ draw(); }});

    renderEvents();
    updateSelectionDetails();
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
    playback_future_frames: int = 0,
    map_crop_margin_m: float = 0.0,
) -> Path:
    context, result = build_context_and_result(path, scenario_index, scenario_id)
    payload = build_viewer_payload(
        context,
        result,
        map_feature_limit=map_feature_limit,
        playback_future_frames=playback_future_frames,
        map_crop_margin_m=map_crop_margin_m,
    )
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


def build_review_payload_index(payload_dir: Path) -> dict:
    json_files = sorted(payload_dir.glob("*.json"))
    review_files = []
    diagnostics = []
    total_review_events = 0

    for json_path in json_files:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            diagnostics.append({"file": json_path.name, "error": str(exc)})
            continue

        if not isinstance(data, dict):
            continue

        review_indices = data.get("review_event_indices") or []
        review_events = data.get("review_events") or []

        if not review_indices and not review_events:
            continue

        events = data.get("events") or []
        if review_indices:
            re_list = [events[i] for i in review_indices if i < len(events)]
        else:
            re_list = review_events

        tag_counts: dict[str, int] = {}
        for ev in re_list:
            tag = ev.get("tag_name", "")
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        first_frame = re_list[0].get("frame_index") if re_list else None
        first_ts = re_list[0].get("timestamp_seconds") if re_list else None

        review_files.append({
            "file": json_path.name,
            "path": json_path.name,
            "viewer_path": "",
            "scenario_id": data.get("scenario_id", ""),
            "source": data.get("source", ""),
            "review_event_count": len(re_list),
            "review_tag_counts": tag_counts,
            "review_tags": sorted(tag_counts.keys()),
            "first_review_frame_index": first_frame,
            "first_review_timestamp_seconds": first_ts,
            "total_events": len(events),
        })
        total_review_events += len(re_list)

    return {
        "payload_dir": str(payload_dir),
        "files": review_files,
        "stats": {
            "payload_files": len(json_files),
            "review_files": len(review_files),
            "review_events": total_review_events,
        },
        "diagnostics": diagnostics,
    }


def render_review_index_html(index: dict) -> str:
    stats = index.get("stats", {})
    files = index.get("files", [])
    index_json = json.dumps(index, ensure_ascii=False).replace("</", "<\\/")
    rows = ""
    for i, f in enumerate(files):
        tags = ", ".join(f.get("review_tags", []))
        rows += (
            f'<div class="row" data-file="{f["file"]}" onclick="selectFile({i})">'
            f'<div class="name">{f["file"]}</div>'
            f'<div class="meta">{f.get("scenario_id", "")}</div>'
            f'<div class="meta">{tags} | {f.get("review_event_count", 0)} events</div>'
            f'</div>\n'
        )
    first_viewer = files[0]["viewer_path"] if files else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Review Index</title>
  <style>
    body {{ margin: 0; font: 13px/1.4 system-ui, sans-serif; display: flex; height: 100vh; }}
    #reviewFileList {{ width: 340px; overflow: auto; border-right: 1px solid #d8dde6; background: #fff; }}
    .header {{ padding: 12px; border-bottom: 1px solid #d8dde6; font-weight: 650; }}
    .row {{ padding: 8px 12px; border-bottom: 1px solid #eee; cursor: pointer; border-left: 3px solid transparent; }}
    .row:hover {{ background: #f0fdfa; }}
    .row.selected {{ background: #dff8f0; border-left-color: #0f766e; }}
    .row .name {{ font-weight: 600; }}
    .row .meta {{ color: #64748b; font-size: 11px; margin-top: 2px; }}
    #viewerFrame {{ flex: 1; border: none; }}
  </style>
</head>
<body>
  <div id="reviewFileList">
    <div class="header">Review Files ({stats.get("review_files", 0)} / {stats.get("payload_files", 0)}) | {stats.get("review_events", 0)} events</div>
    {rows}
  </div>
  <iframe id="viewerFrame" src="{first_viewer}"></iframe>
  <script id="reviewFileIndex" type="application/json">{index_json}</script>
  <script>
    function selectFile(i) {{
      const files = JSON.parse(document.getElementById('reviewFileIndex').textContent).files;
      document.getElementById('viewerFrame').src = files[i].viewer_path;
      document.querySelectorAll('#reviewFileList .row').forEach((row, index) => {{
        row.classList.toggle('selected', index === i);
      }});
    }}
    if ({len(files)} > 0) selectFile(0);
  </script>
</body>
</html>"""


def render_review_index_from_payload_dir(
    payload_dir: Path,
    output: Path,
    viewer_dir: Path | None = None,
) -> Path:
    index = build_review_payload_index(payload_dir)

    if viewer_dir is None:
        viewer_dir = output.parent / "review_viewers"
    viewer_dir.mkdir(parents=True, exist_ok=True)

    for entry in index["files"]:
        payload_path = payload_dir / entry["file"]
        viewer_path = viewer_dir / (payload_path.stem + ".html")
        render_viewer_from_payload(payload_path, viewer_path)
        entry["viewer_path"] = os.path.relpath(viewer_path, output.parent)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_review_index_html(index), encoding="utf-8")
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
