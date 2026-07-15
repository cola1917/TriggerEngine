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
        self.assertEqual(payload["review_summary"]["primary_event_count"], 1)
        self.assertEqual(payload["review_summary"]["unique_target_count"], 1)
        self.assertEqual(
            payload["review_summary"]["event_counts_by_tag"],
            {"cut_in_confirmed": 1},
        )
        self.assertEqual(
            payload["review_event_groups_by_tag"],
            [
                {
                    "tag_name": "cut_in_confirmed",
                    "event_indices": [0],
                    "count": 1,
                }
            ],
        )

    def test_review_event_groups_by_tag_preserve_review_priority_order(self):
        from tools.export_viewer import build_viewer_payload

        events = (
            TagEvent("scenario-viewer", "unit", 1, 0.1, "cut_in_confirmed", "agent_pair", "1:2", True, "r1", {"intent": "review"}),
            TagEvent("scenario-viewer", "unit", 2, 0.2, "sdc_hard_braking", "sdc_pair", "1:3", True, "r2", {"intent": "review"}),
            TagEvent("scenario-viewer", "unit", 0, 0.0, "cut_in_confirmed", "agent_pair", "1:4", True, "r3", {"intent": "review"}),
            TagEvent("scenario-viewer", "unit", 2, 0.2, "adjacent_vehicle", "agent_pair", "1:2", True, "r4", {"intent": "supporting"}),
        )
        result = EngineResult(
            scenario_id="scenario-viewer",
            source="unit",
            plan_id="classic_v1",
            events=events,
            stats=EngineStats(3, 0, 1, 1, len(events)),
            diagnostics=(),
        )

        payload = build_viewer_payload(make_context(), result)

        self.assertEqual(payload["review_event_indices"], [0, 2, 1])
        self.assertEqual(
            payload["review_event_groups_by_tag"],
            [
                {"tag_name": "cut_in_confirmed", "event_indices": [0, 2], "count": 2},
                {"tag_name": "sdc_hard_braking", "event_indices": [1], "count": 1},
            ],
        )

    def test_map_crop_keeps_large_feature_covering_bounds(self):
        from tools.export_viewer import _feature_intersects_bounds
        from trigger_engine.data.frames import MapFeature, Point3D

        feature = MapFeature(
            feature_id=1,
            feature_type="drivable_area",
            polyline=(),
            polygon=(
                Point3D(-100.0, -100.0, 0.0),
                Point3D(100.0, -100.0, 0.0),
                Point3D(100.0, 100.0, 0.0),
                Point3D(-100.0, 100.0, 0.0),
            ),
            properties={},
        )

        self.assertTrue(
            _feature_intersects_bounds(
                feature,
                {"min_x": -5.0, "max_x": 5.0, "min_y": -5.0, "max_y": 5.0},
            )
        )

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
        self.assertEqual(payload["review_summary"]["candidate_event_count"], 1)
        self.assertEqual(payload["review_summary"]["event_counts_by_risk"], {"medium": 1})

    def test_medium_hard_braking_event_stays_default_review_with_subtype(self):
        from tools.export_viewer import build_viewer_payload

        event = TagEvent(
            scenario_id="scenario-viewer",
            source="unit",
            frame_index=2,
            timestamp_seconds=0.2,
            tag_name="sdc_hard_braking",
            subject_type="sdc_pair",
            subject_id="1:2",
            value=True,
            rule_id="sdc_hard_braking",
            metadata={
                "intent": "review",
                "risk_level": "medium",
                "traffic_control_context": True,
                "review_subtype": "sdc_traffic_light_braking",
            },
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

        self.assertEqual(payload["review_event_indices"], [0])
        self.assertEqual(payload["event_groups"]["primary"], [0])
        self.assertEqual(payload["review_summary"]["event_counts_by_risk"], {"medium": 1})

    def test_event_explanation_extracts_operator_metrics(self):
        from tools.export_viewer import event_explanation

        event = TagEvent(
            scenario_id="scenario-viewer",
            source="unit",
            frame_index=2,
            timestamp_seconds=0.2,
            tag_name="vru_close_interaction",
            subject_type="sdc_pair",
            subject_id="1:20",
            value=True,
            rule_id="vru_close_interaction",
            metadata={
                "intent": "review",
                "target_id": 20,
                "risk_level": "high",
                "risk_reasons": ("low_ttc",),
                "operator_metadata": {
                    "predicate.vru_close_interaction": {
                        "distance_m": 4.2,
                        "ttc_s": 1.1,
                        "vru_type": "pedestrian",
                    }
                },
            },
        )

        explanation = event_explanation(event)

        self.assertEqual(explanation["target_id"], "20")
        self.assertEqual(explanation["risk_level"], "high")
        self.assertEqual(explanation["metrics"]["distance_m"], 4.2)
        self.assertEqual(explanation["metrics"]["ttc_s"], 1.1)

    def test_event_explanation_extracts_temporal_support_metrics(self):
        from tools.export_viewer import event_explanation

        event = TagEvent(
            scenario_id="scenario-viewer",
            source="unit",
            frame_index=8,
            timestamp_seconds=0.8,
            tag_name="cut_in_confirmed",
            subject_type="agent_pair",
            subject_id="1:2",
            value=True,
            rule_id="cut_in_confirmed",
            metadata={
                "intent": "review",
                "supporting_event_metadata": (
                    {
                        "tag_name": "same_path_overlap",
                        "frame_index": 8,
                        "timestamp_seconds": 0.8,
                        "metadata": {
                            "operator_metadata": {
                                "predicate.same_path_overlap": {
                                    "longitudinal_m": 8.0,
                                    "lateral_m": 1.2,
                                }
                            }
                        },
                    },
                ),
            },
        )

        explanation = event_explanation(event)

        self.assertEqual(explanation["metrics"]["longitudinal_m"], 8.0)
        self.assertEqual(explanation["metrics"]["lateral_m"], 1.2)

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

    def test_rendered_viewer_groups_review_events_by_tag_with_expandable_sections(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context(), make_result())
        html = render_viewer_html(payload)

        self.assertIn("review_event_groups_by_tag", html)
        self.assertIn("event-tag-group", html)
        self.assertIn("<details", html)
        self.assertIn("renderEventGroups", html)
        self.assertIn("bboxIntersects", html)

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
