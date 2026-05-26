import unittest

from tests.test_export_viewer_contract import make_context, make_result
from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, MapFeature, Point3D
from trigger_engine.engine.trigger_engine import EngineResult, EngineStats
from trigger_engine.rules.events import TagEvent


def agent(track_id, step, x, y, valid=True):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=step * 0.1,
        center=Point3D(x, y, 0.0),
        velocity_x=1.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=valid,
    )


def typed_agent(track_id, step, x, y, object_type):
    base = agent(track_id, step, x, y)
    return AgentState(
        track_id=base.track_id,
        track_index=base.track_index,
        object_type=object_type,
        timestamp_seconds=base.timestamp_seconds,
        center=base.center,
        velocity_x=base.velocity_x,
        velocity_y=base.velocity_y,
        heading=base.heading,
        length=1.0 if object_type != "vehicle" else base.length,
        width=0.8 if object_type != "vehicle" else base.width,
        height=base.height,
        valid=base.valid,
    )


def frame(step, phase, x=0.0, y=0.0):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-review-v2",
            step_index=step,
            timestamp_seconds=step * 0.1,
            phase=phase,
            agent_states=(
                agent(1, step, x + step, y),
                agent(2, step, x + step + 5.0, y + 1.0),
            ),
            traffic_lights=(),
        ),
        visibility="current" if phase == "current" else ("future" if phase == "future" else "observed"),
        available_modalities=frozenset({"agents"}),
    )


def make_context_with_future_and_map():
    observed = (frame(0, "history"), frame(1, "history"))
    current = frame(2, "current")
    future = (frame(3, "future"), frame(4, "future"), frame(5, "future"))
    near_feature = MapFeature(
        feature_id=1,
        feature_type="lane",
        polyline=(Point3D(-5.0, -5.0, 0.0), Point3D(20.0, 5.0, 0.0)),
        polygon=(),
        properties={},
    )
    far_feature = MapFeature(
        feature_id=2,
        feature_type="lane",
        polyline=(Point3D(10000.0, 10000.0, 0.0), Point3D(10100.0, 10100.0, 0.0)),
        polygon=(),
        properties={},
    )
    return AlignmentContext(
        scenario_id="scenario-review-v2",
        watermark=Watermark("scenario-review-v2", 2, 0.2),
        observed_frames=observed,
        current_frame=current,
        future_frames=future,
        input_frames=observed + (current,),
        source="unit",
        map_features={1: near_feature, 2: far_feature},
    )


def make_context_with_invalid_future_agent_and_many_near_map_features():
    observed = (frame(0, "history", x=1000.0, y=2000.0),)
    current = frame(1, "current", x=1000.0, y=2000.0)
    future = (
        AlignedFrame(
            frame=Frame(
                scenario_id="scenario-review-v2",
                step_index=2,
                timestamp_seconds=0.2,
                phase="future",
                agent_states=(agent(99, 2, 0.0, 0.0, valid=False),),
                traffic_lights=(),
            ),
            visibility="future",
            available_modalities=frozenset({"agents"}),
        ),
    )
    map_features = {
        i: MapFeature(
            feature_id=i,
            feature_type="lane",
            polyline=(
                Point3D(1000.0 + i, 2000.0, 0.0),
                Point3D(1001.0 + i, 2000.0, 0.0),
            ),
            polygon=(),
            properties={},
        )
        for i in range(5)
    }
    return AlignmentContext(
        scenario_id="scenario-review-v2",
        watermark=Watermark("scenario-review-v2", 1, 0.1),
        observed_frames=observed,
        current_frame=current,
        future_frames=future,
        input_frames=observed + (current,),
        source="unit",
        map_features=map_features,
    )


def make_mixed_result():
    events = (
        TagEvent(
            "scenario-review-v2",
            "unit",
            2,
            0.2,
            "cut_in_confirmed",
            "agent_pair",
            "1:2",
            True,
            "cut_in_confirmed",
            {
                "temporal_kind": "sequence",
                "source_tags": ("adjacent_vehicle", "cut_in_lateral_approach", "same_path_overlap"),
                "supporting_frame_indices": (0, 1, 2),
            },
        ),
        TagEvent(
            "scenario-review-v2",
            "unit",
            1,
            0.1,
            "adjacent_vehicle",
            "agent_pair",
            "1:2",
            True,
            "adjacent_vehicle",
            {},
        ),
        TagEvent(
            "scenario-review-v2",
            "unit",
            0,
            0.0,
            "vehicle_stopped",
            "agent",
            1,
            True,
            "vehicle_stopped",
            {},
        ),
    )
    return EngineResult(
        scenario_id="scenario-review-v2",
        source="unit",
        plan_id="classic_v1",
        events=events,
        stats=EngineStats(
            input_frames=3,
            future_frames=3,
            single_frame_rules=9,
            temporal_rules=7,
            events_emitted=len(events),
        ),
        diagnostics=(),
    )


class ReviewViewerV2ContractTests(unittest.TestCase):
    def test_payload_includes_future_playback_frames(self):
        from tools.export_viewer import build_viewer_payload

        payload = build_viewer_payload(
            make_context_with_future_and_map(),
            make_mixed_result(),
            playback_future_frames=2,
        )

        self.assertEqual(len(payload["frames"]), 5)
        self.assertEqual(payload["playback"]["history_frame_count"], 3)
        self.assertEqual(payload["playback"]["future_frame_count"], 2)
        self.assertEqual(payload["playback"]["current_frame_index"], 2)
        self.assertEqual(payload["frames"][-1]["frame_index"], 4)

    def test_payload_groups_primary_supporting_and_debug_events(self):
        from tools.export_viewer import build_viewer_payload

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())

        self.assertEqual([event["tag_name"] for event in payload["review_events"]], ["cut_in_confirmed"])
        self.assertEqual(payload["event_groups"]["primary"], [0])
        self.assertEqual(payload["event_groups"]["supporting"], [1])
        self.assertEqual(payload["event_groups"]["debug"], [2])

    def test_map_features_are_cropped_by_agent_or_event_bounds(self):
        from tools.export_viewer import build_viewer_payload

        payload = build_viewer_payload(
            make_context_with_future_and_map(),
            make_mixed_result(),
            map_crop_margin_m=30.0,
        )

        self.assertEqual([feature["feature_id"] for feature in payload["map_features"]], [1])
        scenario_bounds = payload["view"]["scenario_bounds"]
        self.assertLess(scenario_bounds["max_x"] - scenario_bounds["min_x"], 100.0)
        self.assertIn("0", payload["view"]["event_bounds_by_event_index"])

    def test_bounds_ignore_invalid_agents_and_crop_still_respects_feature_limit(self):
        from tools.export_viewer import build_viewer_payload

        payload = build_viewer_payload(
            make_context_with_invalid_future_agent_and_many_near_map_features(),
            make_mixed_result(),
            map_feature_limit=2,
            playback_future_frames=1,
            map_crop_margin_m=80.0,
        )

        scenario_bounds = payload["view"]["scenario_bounds"]
        self.assertGreater(scenario_bounds["min_x"], 900.0)
        self.assertGreater(scenario_bounds["min_y"], 1900.0)
        self.assertEqual(len(payload["map_features"]), 2)

    def test_event_bounds_ignore_invalid_agents(self):
        from tools.export_viewer import build_viewer_payload

        result = EngineResult(
            scenario_id="scenario-review-v2",
            source="unit",
            plan_id="classic_v1",
            events=(
                TagEvent(
                    "scenario-review-v2",
                    "unit",
                    1,
                    0.1,
                    "vehicle_stopped_for_3_frames",
                    "agent",
                    99,
                    True,
                    "vehicle_stopped_for_3_frames",
                    {},
                ),
            ),
            stats=EngineStats(2, 1, 0, 1, 1),
            diagnostics=(),
        )

        payload = build_viewer_payload(
            make_context_with_invalid_future_agent_and_many_near_map_features(),
            result,
            playback_future_frames=1,
        )

        self.assertNotIn("0", payload["view"]["event_bounds_by_event_index"])

    def test_rendered_viewer_exposes_review_controls_and_sequence_timeline(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("eventGroupSelect", html)
        self.assertIn("sequenceTimeline", html)
        self.assertNotIn("viewModeSelect", html)
        self.assertNotIn("fit scenario", html)
        self.assertNotIn("fit map", html)

    def test_rendered_viewer_defaults_to_review_events_without_losing_event_indexes(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("let currentEventGroup = 'review'", html)
        self.assertNotIn("payload.events.indexOf(e)", html)

    def test_rendered_viewer_uses_payload_view_bounds_for_projection_modes(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("payload.view", html)
        self.assertIn("event_bounds_by_event_index", html)
        self.assertIn("scenario_bounds", html)

    def test_rendered_viewer_opens_on_a_readable_selected_review_event(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("review_event_indices", payload)
        self.assertEqual(payload["review_event_indices"], [0])
        self.assertNotIn("currentViewMode", html)
        self.assertIn("let selectedEventIndex = firstReviewEventIndex()", html)
        self.assertIn("updateSelectionDetails()", html)
        self.assertIn("featureIntersectsBounds", html)
        self.assertIn("drawFocalHalo", html)

    def test_review_default_prioritizes_pair_events_when_available(self):
        from tools.export_viewer import build_viewer_payload

        result = EngineResult(
            scenario_id="scenario-review-v2",
            source="unit",
            plan_id="classic_v1",
            events=(
                TagEvent(
                    "scenario-review-v2",
                    "unit",
                    1,
                    0.1,
                    "vehicle_stopped_for_3_frames",
                    "agent",
                    1,
                    True,
                    "vehicle_stopped_for_3_frames",
                    {},
                ),
                TagEvent(
                    "scenario-review-v2",
                    "unit",
                    2,
                    0.2,
                    "cut_in_confirmed",
                    "agent_pair",
                    "1:2",
                    True,
                    "cut_in_confirmed",
                    {},
                ),
            ),
            stats=EngineStats(3, 0, 1, 1, 2),
            diagnostics=(),
        )

        payload = build_viewer_payload(make_context_with_future_and_map(), result)

        self.assertEqual(payload["review_event_indices"], [1])
        self.assertEqual(payload["event_groups"]["debug"], [0])

    def test_sustained_stopped_events_do_not_enter_default_review(self):
        from tools.export_viewer import build_viewer_payload

        result = EngineResult(
            scenario_id="scenario-review-v2",
            source="unit",
            plan_id="classic_v1",
            events=(
                TagEvent(
                    "scenario-review-v2",
                    "unit",
                    1,
                    0.1,
                    "vehicle_stopped_for_3_frames",
                    "agent",
                    1,
                    True,
                    "vehicle_stopped_for_3_frames",
                    {},
                ),
            ),
            stats=EngineStats(3, 0, 1, 1, 1),
            diagnostics=(),
        )

        payload = build_viewer_payload(make_context_with_future_and_map(), result)

        self.assertEqual(payload["review_event_indices"], [])
        self.assertEqual(payload["review_events"], [])
        self.assertEqual(payload["event_groups"]["debug"], [0])

    def test_review_list_uses_prioritized_review_event_order(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("return (payload.review_event_indices || [])", html)
        self.assertNotIn("const reviewSet = new Set", html)

    def test_rendered_viewer_uses_bev_scene_visual_language(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("eventFrameTransform", html)
        self.assertIn("worldToEventLocal", html)
        self.assertIn("drawLaneRibbon", html)
        self.assertIn("drawAgentTrajectory", html)
        self.assertIn("drawHeadingArrow", html)
        self.assertIn("drawScaleBar", html)
        self.assertIn("drawEgoReticle", html)
        self.assertIn("renderQualityMode", html)

    def test_fit_event_view_is_compact_and_role_readable(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn('<canvas id="canvas" width="720" height="420">', html)
        self.assertIn("review-shell", html)

    def test_rendered_viewer_distinguishes_vru_target_types(self):
        from tools.export_viewer import render_viewer_html

        payload = {
            "scenario_id": "scenario-vru-view",
            "source": "unit",
            "plan_id": "classic_v1",
            "frames": [
                {
                    "frame_index": 0,
                    "timestamp_seconds": 0.0,
                    "phase": "current",
                    "agents": [
                        {
                            "track_id": 1,
                            "track_index": 1,
                            "object_type": "vehicle",
                            "valid": True,
                            "x": 0.0,
                            "y": 0.0,
                            "z": 0.0,
                            "heading": 0.0,
                            "length": 4.0,
                            "width": 1.8,
                            "height": 1.5,
                            "velocity_x": 1.0,
                            "velocity_y": 0.0,
                        },
                        {
                            "track_id": 2,
                            "track_index": 2,
                            "object_type": "pedestrian",
                            "valid": True,
                            "x": 5.0,
                            "y": 1.0,
                            "z": 0.0,
                            "heading": 0.0,
                            "length": 1.0,
                            "width": 0.8,
                            "height": 1.5,
                            "velocity_x": 0.0,
                            "velocity_y": 0.0,
                        },
                    ],
                    "traffic_lights": [],
                }
            ],
            "events": [
                {
                    "scenario_id": "scenario-vru-view",
                    "source": "unit",
                    "frame_index": 0,
                    "timestamp_seconds": 0.0,
                    "tag_name": "vru_close_interaction",
                    "subject_type": "agent_pair",
                    "subject_id": "1:2",
                    "value": True,
                    "rule_name": "vru_close_interaction",
                    "metadata": {"intent": "review"},
                }
            ],
            "review_events": [],
            "review_event_indices": [0],
            "event_groups": {"primary": [0], "supporting": [], "debug": []},
            "map_features": [],
            "view": {"scenario_bounds": {"min_x": -10, "max_x": 10, "min_y": -10, "max_y": 10}},
            "stats": {},
            "diagnostics": [],
        }

        html = render_viewer_html(payload)

        self.assertIn("agent.object_type === 'pedestrian'", html)
        self.assertIn("agent.object_type === 'cyclist'", html)
        self.assertIn("agentLabel", html)
        self.assertIn("event-card", html)
        self.assertIn("scene-panel", html)
        self.assertIn("summary-panel", html)
        self.assertIn("max-width: 100vw", html)
        self.assertIn("min-height: 520px", html)
        self.assertNotIn("height: 100%", html)
        self.assertNotIn("viewModeSelect", html)
        self.assertNotIn("currentViewMode", html)
        self.assertIn("roleForAgent", html)
        self.assertIn("drawRoleBadge", html)
        self.assertIn("egoColor", html)
        self.assertIn("targetColor", html)
        self.assertIn("EGO", html)
        self.assertIn("TARGET", html)

    def test_compact_event_card_uses_summary_instead_of_default_raw_json(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn('id="eventSummary"', html)
        self.assertIn('id="summaryTag"', html)
        self.assertIn('id="summaryScenario"', html)
        self.assertIn('id="summaryFrame"', html)
        self.assertIn('id="summaryTime"', html)
        self.assertIn('id="summaryEgo"', html)
        self.assertIn('id="summaryTarget"', html)
        self.assertIn('id="summaryRule"', html)
        self.assertIn('id="rawEventDetails"', html)
        self.assertIn("<details", html)
        self.assertNotIn('<pre id="details"></pre>', html)
        self.assertNotIn("details.textContent = JSON.stringify(event, null, 2)", html)

    def test_summary_panel_derives_ego_and_target_from_selected_event(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("function updateEventSummary", html)
        self.assertIn("summaryEgo", html)
        self.assertIn("summaryTarget", html)
        self.assertIn("event.subject_type === 'agent_pair'", html)
        self.assertIn("event.subject_id", html)
        self.assertIn("n/a", html)

    def test_rendered_viewer_does_not_reference_missing_dom_nodes(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        if "document.getElementById('eventCount')" in html:
            self.assertIn('id="eventCount"', html)

    def test_event_local_transform_is_used_by_projection(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        project_start = html.index("function project(")
        project_end = html.index("function featureIntersectsBounds", project_start)
        project_source = html[project_start:project_end]

        self.assertIn("eventFrameTransform(selectedEvent())", project_source)
        self.assertIn("worldToEventLocal", project_source)
        self.assertNotIn("currentViewMode", project_source)

    def test_export_review_payload_cli_accepts_future_and_map_crop_options(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from tools import export_review_payload as cli

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "payload.json"
            with patch.object(cli, "export_review_payload") as export_mock:
                export_mock.return_value = output_path

                result = cli.main(
                    [
                        "input.tfrecord",
                        "-o",
                        str(output_path),
                        "--scenario-index",
                        "3",
                        "--future-frames",
                        "12",
                        "--map-crop-margin-m",
                        "90",
                    ]
                )

        self.assertEqual(result, 0)
        export_mock.assert_called_once()
        self.assertEqual(export_mock.call_args.kwargs["playback_future_frames"], 12)
        self.assertEqual(export_mock.call_args.kwargs["map_crop_margin_m"], 90.0)

    def test_existing_payload_builder_call_remains_backward_compatible(self):
        from tools.export_viewer import build_viewer_payload

        payload = build_viewer_payload(make_context(), make_result())

        self.assertIn("frames", payload)
        self.assertIn("events", payload)


if __name__ == "__main__":
    unittest.main()
