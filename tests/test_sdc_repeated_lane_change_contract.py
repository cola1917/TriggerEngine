import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, MapFeature, Point3D


def agent(track_id, x=0.0, y=0.0, vx=8.0, vy=0.0, heading=0.0):
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
        valid=True,
    )


def lane(feature_id, y, lane_type="surface_street", speed_limit_mph=35.0):
    return MapFeature(
        feature_id=feature_id,
        feature_type="lane",
        polyline=(Point3D(-20.0, y, 0.0), Point3D(40.0, y, 0.0)),
        polygon=(),
        properties={
            "lane_type": lane_type,
            "speed_limit_mph": speed_limit_mph,
        },
    )


def lane_segment(feature_id, x0, x1, y=0.0, entry_lanes=(), exit_lanes=()):
    return MapFeature(
        feature_id=feature_id,
        feature_type="lane",
        polyline=(Point3D(x0, y, 0.0), Point3D(x1, y, 0.0)),
        polygon=(),
        properties={
            "lane_type": "surface_street",
            "speed_limit_mph": 35.0,
            "entry_lanes": tuple(entry_lanes),
            "exit_lanes": tuple(exit_lanes),
        },
    )


def aligned_frame(step_index, sdc):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-sdc-repeated-lane-change",
            step_index=step_index,
            timestamp_seconds=step_index * 0.5,
            phase="current" if step_index >= 4 else "history",
            agent_states=(sdc,),
            traffic_lights=(),
        ),
        visibility="current" if step_index >= 4 else "observed",
        available_modalities=frozenset({"agents", "valid_agents", "map"}),
    )


def context(frames, map_features=None):
    return AlignmentContext(
        scenario_id="scenario-sdc-repeated-lane-change",
        watermark=Watermark(
            "scenario-sdc-repeated-lane-change",
            frames[-1].frame.step_index,
            frames[-1].frame.timestamp_seconds,
        ),
        observed_frames=tuple(frames[:-1]),
        current_frame=frames[-1],
        future_frames=(),
        input_frames=tuple(frames),
        source="unit",
        map_features=map_features if map_features is not None else {
            10: lane(10, 0.0),
            11: lane(11, 3.5),
            12: lane(12, 7.0),
        },
        sdc_track_index=1,
        sdc_track_id=1,
    )


def classic_engine():
    from trigger_engine.engine.registry import RuleRegistry
    from trigger_engine.engine.trigger_engine import TriggerEngine
    from trigger_engine.operators.registry import OperatorRegistry
    from trigger_engine.scenarios.classic import register_classic_scenario_pack

    operators = OperatorRegistry()
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    return TriggerEngine(operators, rules)


class SdcRepeatedLaneChangeContractTests(unittest.TestCase):
    def test_builtin_lane_change_operators_are_registered(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)

        self.assertEqual(registry.get("predicate.sdc_lane_changed").subject_type, "agent")
        self.assertEqual(registry.get("predicate.sdc_repeated_lane_change").subject_type, "agent")

    def test_classic_pack_defines_sdc_repeated_lane_change_without_highway_rule(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rule_set = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML)
        by_id = {rule.rule_id: rule for rule in rule_set.rules}

        rule = by_id["sdc_repeated_lane_change"]
        self.assertEqual(rule.kind, "single_frame")
        self.assertEqual(rule.subject_type, "sdc_agent")
        self.assertEqual(rule.emit.tag_name, "sdc_repeated_lane_change")
        self.assertEqual(rule.emit.intent, "review")
        self.assertNotIn("sdc_highway_repeated_lane_change", by_id)

    def test_sdc_repeated_lane_change_emits_review_for_two_lane_changes(self):
        frames = (
            aligned_frame(0, agent(1, x=0.0, y=0.0)),
            aligned_frame(1, agent(1, x=4.0, y=0.1)),
            aligned_frame(2, agent(1, x=8.0, y=3.5)),
            aligned_frame(3, agent(1, x=12.0, y=3.6)),
            aligned_frame(4, agent(1, x=16.0, y=7.0)),
            aligned_frame(5, agent(1, x=20.0, y=7.1)),
        )

        result = classic_engine().evaluate(context(frames))
        review_events = [
            event for event in result.events
            if event.tag_name == "sdc_repeated_lane_change"
        ]

        self.assertEqual(len(review_events), 1)
        self.assertEqual(review_events[0].metadata["intent"], "review")

    def test_sdc_repeated_lane_change_ignores_unstable_single_frame_lane_jump(self):
        frames = (
            aligned_frame(0, agent(1, x=0.0, y=0.0)),
            aligned_frame(1, agent(1, x=4.0, y=0.1)),
            aligned_frame(2, agent(1, x=8.0, y=3.5)),
            aligned_frame(3, agent(1, x=12.0, y=3.6)),
            aligned_frame(4, agent(1, x=16.0, y=7.0)),
        )

        result = classic_engine().evaluate(context(frames))
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertNotIn("sdc_repeated_lane_change", review_tags)

    def test_sdc_repeated_lane_change_ignores_longitudinal_lane_segment_transitions(self):
        frames = (
            aligned_frame(0, agent(1, x=0.0, y=0.0)),
            aligned_frame(1, agent(1, x=4.0, y=0.0)),
            aligned_frame(2, agent(1, x=8.0, y=0.0)),
            aligned_frame(3, agent(1, x=12.0, y=0.0)),
            aligned_frame(4, agent(1, x=16.0, y=0.0)),
            aligned_frame(5, agent(1, x=20.0, y=0.0)),
        )
        map_features = {
            10: lane_segment(10, -5.0, 7.0, exit_lanes=(11,)),
            11: lane_segment(11, 7.0, 15.0, entry_lanes=(10,), exit_lanes=(12,)),
            12: lane_segment(12, 15.0, 25.0, entry_lanes=(11,)),
        }

        result = classic_engine().evaluate(context(frames, map_features=map_features))
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertNotIn("sdc_repeated_lane_change", review_tags)

    def test_sdc_single_lane_change_does_not_emit_repeated_lane_change(self):
        frames = (
            aligned_frame(0, agent(1, x=0.0, y=0.0)),
            aligned_frame(1, agent(1, x=4.0, y=0.0)),
            aligned_frame(2, agent(1, x=8.0, y=3.5)),
            aligned_frame(3, agent(1, x=12.0, y=3.5)),
            aligned_frame(4, agent(1, x=16.0, y=3.5)),
        )

        result = classic_engine().evaluate(context(frames))
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertNotIn("sdc_repeated_lane_change", review_tags)

    def test_sdc_repeated_lane_change_requires_map_features(self):
        frames = (
            aligned_frame(0, agent(1, x=0.0, y=0.0)),
            aligned_frame(1, agent(1, x=4.0, y=3.5)),
            aligned_frame(2, agent(1, x=8.0, y=7.0)),
        )

        result = classic_engine().evaluate(context(frames, map_features={}))
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertNotIn("sdc_repeated_lane_change", review_tags)


if __name__ == "__main__":
    unittest.main()
