import json
import re
import tempfile
import unittest
from pathlib import Path

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D
from trigger_engine.engine.trigger_engine import EngineResult, EngineStats
from trigger_engine.rules.events import TagEvent


def agent(track_id, x, y):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(x, y, 0.0),
        velocity_x=1.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def make_context():
    frames = []
    for step in range(3):
        frame = Frame(
            scenario_id="scenario-viewer",
            step_index=step,
            timestamp_seconds=step * 0.1,
            phase="current" if step == 2 else "history",
            agent_states=(agent(1, step, 0.0), agent(2, step + 5.0, 1.0)),
            traffic_lights=(),
        )
        frames.append(
            AlignedFrame(
                frame=frame,
                visibility="current" if step == 2 else "observed",
                available_modalities=frozenset({"agents"}),
            )
        )
    return AlignmentContext(
        scenario_id="scenario-viewer",
        watermark=Watermark("scenario-viewer", 2, 0.2),
        observed_frames=tuple(frames[:2]),
        current_frame=frames[2],
        future_frames=(),
        input_frames=tuple(frames),
        source="unit",
    )


def make_result():
    events = (
        TagEvent(
            scenario_id="scenario-viewer",
            source="unit",
            frame_index=2,
            timestamp_seconds=0.2,
            tag_name="cut_in_confirmed",
            subject_type="agent_pair",
            subject_id="1:2",
            value=True,
            rule_id="cut_in_confirmed",
            metadata={
                "supporting_frame_indices": (0, 1, 2),
                "source_tags": ("adjacent_vehicle", "cut_in_lateral_approach", "same_path_overlap"),
            },
        ),
    )
    return EngineResult(
        scenario_id="scenario-viewer",
        source="unit",
        plan_id="classic_v1",
        events=events,
        stats=EngineStats(
            input_frames=3,
            future_frames=0,
            single_frame_rules=1,
            temporal_rules=1,
            events_emitted=1,
        ),
        diagnostics=(),
    )


class ExportViewerContractTests(unittest.TestCase):
    def test_build_viewer_payload_contains_frames_events_and_stats(self):
        from tools.export_viewer import build_viewer_payload

        payload = build_viewer_payload(make_context(), make_result())

        self.assertEqual(payload["scenario_id"], "scenario-viewer")
        self.assertEqual(len(payload["frames"]), 3)
        self.assertEqual(payload["frames"][0]["agents"][0]["track_id"], 1)
        self.assertEqual(payload["events"][0]["subject_id"], "1:2")
        self.assertEqual(payload["events"][0]["metadata"]["supporting_frame_indices"], (0, 1, 2))
        self.assertEqual(payload["stats"]["events_emitted"], 1)

    def test_medium_vru_event_is_kept_but_not_default_review(self):
        from tools.export_viewer import build_viewer_payload

        event = TagEvent(
            scenario_id="scenario-viewer",
            source="unit",
            frame_index=2,
            timestamp_seconds=0.2,
            tag_name="vru_close_interaction",
            subject_type="sdc_pair",
            subject_id="1:2",
            value=True,
            rule_id="vru_close_interaction",
            metadata={"intent": "review", "risk_level": "medium"},
        )
        result = EngineResult(
            scenario_id="scenario-viewer",
            source="unit",
            plan_id="classic_v1",
            events=(event,),
            stats=EngineStats(
                input_frames=3,
                future_frames=0,
                single_frame_rules=1,
                temporal_rules=0,
                events_emitted=1,
            ),
            diagnostics=(),
        )

        payload = build_viewer_payload(make_context(), result)

        self.assertEqual(payload["events"][0]["metadata"]["risk_level"], "medium")
        self.assertEqual(payload["review_event_indices"], [])
        self.assertEqual(payload["event_groups"]["supporting"], [0])

    def test_render_viewer_html_embeds_parseable_payload(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context(), make_result())
        html = render_viewer_html(payload)

        self.assertIn("<canvas", html)
        self.assertIn("tagSelect", html)
        match = re.search(
            r'<script id="payload" type="application/json">(.*?)</script>',
            html,
            flags=re.S,
        )
        self.assertIsNotNone(match)
        embedded = json.loads(match.group(1))
        self.assertEqual(embedded["events"][0]["tag_name"], "cut_in_confirmed")

    def test_render_viewer_from_payload_uses_payload_json_without_running_engine(self):
        from tools.export_viewer import (
            build_viewer_payload,
            render_viewer_from_payload,
        )

        payload = build_viewer_payload(make_context(), make_result())
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload_path = Path(tmp_dir) / "payload.json"
            output_path = Path(tmp_dir) / "viewer.html"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            result = render_viewer_from_payload(payload_path, output_path)

            self.assertEqual(result, output_path)
            html = output_path.read_text(encoding="utf-8")
            self.assertIn("scenario-viewer", html)
            self.assertIn("cut_in_confirmed", html)


if __name__ == "__main__":
    unittest.main()
