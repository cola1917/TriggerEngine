import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import (
    AgentState,
    Frame,
    MapFeature,
    Point3D,
    ScenarioBundle,
    TrafficLightState,
)


def agent(track_id, x=0.0, y=0.0, vx=0.0, vy=0.0, heading=0.0, valid=True):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(x, y, 0.0),
        velocity_x=vx,
        velocity_y=vy,
        heading=heading,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=valid,
    )


def red_light():
    return TrafficLightState(
        lane_id=7,
        state="stop",
        stop_point=Point3D(0.0, 0.0, 0.0),
    )


def green_light():
    return TrafficLightState(
        lane_id=7,
        state="go",
        stop_point=Point3D(0.0, 0.0, 0.0),
    )


def lane_feature():
    return MapFeature(
        feature_id=7,
        feature_type="lane",
        polyline=(
            Point3D(-20.0, 0.0, 0.0),
            Point3D(0.0, 0.0, 0.0),
            Point3D(20.0, 0.0, 0.0),
        ),
        polygon=(),
        properties={"lane_type": "surface_street"},
    )


def curved_right_turn_lane_feature():
    return MapFeature(
        feature_id=7,
        feature_type="lane",
        polyline=(
            Point3D(-20.0, 0.0, 0.0),
            Point3D(0.0, 0.0, 0.0),
            Point3D(5.0, 0.0, 0.0),
            Point3D(5.0, 5.0, 0.0),
        ),
        polygon=(),
        properties={"lane_type": "surface_street"},
    )


def aligned_frame(step_index, agents, traffic_lights=(red_light(),)):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-red-light-map",
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase="current" if step_index == 1 else "history",
            agent_states=agents,
            traffic_lights=traffic_lights,
        ),
        visibility="current" if step_index == 1 else "observed",
        available_modalities=frozenset({"agents", "valid_agents", "traffic_lights", "map"}),
    )


def map_context(frames, map_features=None):
    return AlignmentContext(
        scenario_id="scenario-red-light-map",
        watermark=Watermark("scenario-red-light-map", frames[-1].frame.step_index, frames[-1].frame.timestamp_seconds),
        observed_frames=tuple(frames[:-1]),
        current_frame=frames[-1],
        future_frames=(),
        input_frames=tuple(frames),
        source="unit",
        map_features=map_features if map_features is not None else {7: lane_feature()},
        sdc_track_index=1,
        sdc_track_id=1,
    )


class RedLightMapSemanticsContractTests(unittest.TestCase):
    def test_alignment_context_carries_map_features_for_map_semantic_rules(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        frames = (
            Frame(
                scenario_id="scenario-red-light-map",
                step_index=0,
                timestamp_seconds=0.0,
                phase="history",
                agent_states=(agent(1, x=-2.0, vx=5.0),),
                traffic_lights=(red_light(),),
            ),
            Frame(
                scenario_id="scenario-red-light-map",
                step_index=1,
                timestamp_seconds=0.1,
                phase="current",
                agent_states=(agent(1, x=2.0, vx=5.0),),
                traffic_lights=(red_light(),),
            ),
        )
        bundle = ScenarioBundle(
            scenario_id="scenario-red-light-map",
            timestamps_seconds=(0.0, 0.1),
            current_time_index=1,
            sdc_track_index=1,
            objects_of_interest=(),
            prediction_targets=(),
            frames=frames,
            map_features={7: lane_feature()},
            source="unit",
            has_lidar_data=False,
        )

        context = ScenarioAlignment().align(bundle)

        self.assertIn(7, context.map_features)
        self.assertEqual(context.map_features[7].feature_type, "lane")
        self.assertIn("map", context.current_frame.available_modalities)

    def test_builtin_red_light_map_operators_are_registered(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)

        self.assertEqual(
            registry.get("predicate.red_light_before_stop_line").subject_type,
            "agent",
        )
        self.assertEqual(
            registry.get("predicate.red_light_after_stop_line").subject_type,
            "agent",
        )

    def test_red_light_stop_line_operators_use_lane_direction_and_light_state(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        before_op = registry.get("predicate.red_light_before_stop_line")
        after_op = registry.get("predicate.red_light_after_stop_line")

        before_agent = agent(1, x=-3.0, y=0.2, vx=5.0, heading=0.0)
        after_agent = agent(2, x=2.0, y=0.2, vx=5.0, heading=0.0)
        off_lane_agent = agent(3, x=2.0, y=4.0, vx=5.0, heading=0.0)
        frame = aligned_frame(0, (before_agent, after_agent, off_lane_agent))
        context = map_context((frame,))

        before_args = {
            "max_lateral_m": 2.0,
            "max_before_stop_line_m": 12.0,
            "min_speed_mps": 0.5,
            "max_heading_delta_rad": 0.7,
        }
        after_args = {
            "max_lateral_m": 2.0,
            "min_after_stop_line_m": 0.5,
            "max_after_stop_line_m": 15.0,
            "min_speed_mps": 0.5,
            "max_heading_delta_rad": 0.7,
        }

        self.assertTrue(before_op.evaluate(context, frame, before_agent, before_args).value)
        self.assertFalse(before_op.evaluate(context, frame, after_agent, before_args).value)
        self.assertTrue(after_op.evaluate(context, frame, after_agent, after_args).value)
        self.assertFalse(after_op.evaluate(context, frame, off_lane_agent, after_args).value)

        green_frame = aligned_frame(0, (after_agent,), traffic_lights=(green_light(),))
        green_context = map_context((green_frame,))
        self.assertFalse(after_op.evaluate(green_context, green_frame, after_agent, after_args).value)

    def test_red_light_stop_line_operators_require_lane_map_feature(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        before_op = registry.get("predicate.red_light_before_stop_line")
        after_op = registry.get("predicate.red_light_after_stop_line")

        subject = agent(1, x=2.0, y=0.1, vx=5.0, heading=0.0)
        frame = aligned_frame(0, (subject,))
        context_without_map = AlignmentContext(
            scenario_id="scenario-red-light-map",
            watermark=Watermark("scenario-red-light-map", 0, 0.0),
            observed_frames=(),
            current_frame=frame,
            future_frames=(),
            input_frames=(frame,),
            source="unit",
            sdc_track_index=1,
            sdc_track_id=1,
        )

        self.assertFalse(
            before_op.evaluate(
                context_without_map,
                frame,
                subject,
                {
                    "max_lateral_m": 2.0,
                    "max_before_stop_line_m": 12.0,
                    "min_speed_mps": 0.5,
                    "max_heading_delta_rad": 0.7,
                },
            ).value
        )
        self.assertFalse(
            after_op.evaluate(
                context_without_map,
                frame,
                subject,
                {
                    "max_lateral_m": 2.0,
                    "min_after_stop_line_m": 0.5,
                    "max_after_stop_line_m": 15.0,
                    "min_speed_mps": 0.5,
                    "max_heading_delta_rad": 0.7,
                },
            ).value
        )

    def test_red_light_crossing_transition_requires_earlier_same_lane_before_state(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        op = registry.get("predicate.red_light_crossing_transition")
        args = {
            "max_lateral_m": 2.0,
            "max_before_stop_line_m": 12.0,
            "min_after_stop_line_m": 0.5,
            "max_after_stop_line_m": 15.0,
            "min_speed_mps": 0.5,
            "max_heading_delta_rad": 0.7,
        }

        after = aligned_frame(1, (agent(1, x=2.0, y=0.1, vx=5.0),))
        after_subject = after.frame.agent_states[0]

        self.assertFalse(op.evaluate(map_context((after,)), after, after_subject, args).value)

        before = aligned_frame(0, (agent(1, x=-3.0, y=0.1, vx=5.0),))
        result = op.evaluate(map_context((before, after)), after, after_subject, args)

        self.assertTrue(result.value)
        self.assertEqual(result.metadata["lane_id"], 7)
        self.assertEqual(result.metadata["before_frame_index"], 0)

    def test_red_light_crossing_transition_rejects_turn_lane_geometry(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        op = registry.get("predicate.red_light_crossing_transition")
        args = {
            "max_lateral_m": 2.0,
            "max_before_stop_line_m": 12.0,
            "min_after_stop_line_m": 0.5,
            "max_after_stop_line_m": 15.0,
            "min_speed_mps": 0.5,
            "max_heading_delta_rad": 0.7,
            "max_lane_heading_change_rad": 0.35,
            "lane_heading_lookahead_m": 15.0,
        }

        before = aligned_frame(0, (agent(1, x=-3.0, y=0.1, vx=5.0),))
        after = aligned_frame(1, (agent(1, x=2.0, y=0.1, vx=5.0),))
        ctx = map_context((before, after), map_features={7: curved_right_turn_lane_feature()})

        self.assertFalse(op.evaluate(ctx, after, after.frame.agent_states[0], args).value)

    def test_classic_pack_defines_map_semantic_red_light_running_rules(self):
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        self.assertIn("red_light_stop_line_approach", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("red_light_stop_line_crossed", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("red_light_running", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("predicate.red_light_before_stop_line", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("predicate.red_light_after_stop_line", CLASSIC_SCENARIO_RULES_YAML)

    def test_classic_pack_emits_red_light_running_only_after_crossing_on_red(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import register_classic_scenario_pack

        operators = OperatorRegistry()
        rules = RuleRegistry(operator_registry=operators)
        register_classic_scenario_pack(operators, rules)

        before = aligned_frame(0, (agent(1, x=-3.0, y=0.1, vx=5.0),))
        after = aligned_frame(1, (agent(1, x=2.0, y=0.1, vx=5.0),))
        ctx = map_context((before, after))
        result = TriggerEngine(operators, rules).evaluate(ctx)
        tags = {event.tag_name for event in result.events if event.subject_id == 1}

        self.assertIn("red_light_stop_line_approach", tags)
        self.assertIn("red_light_stop_line_crossed", tags)
        self.assertIn("red_light_running", tags)


if __name__ == "__main__":
    unittest.main()
