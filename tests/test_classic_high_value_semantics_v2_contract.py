import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, MapFeature, Point3D, TrafficLightState


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


def aligned_frame(scenario_id, step_index, agents, traffic_lights=()):
    return AlignedFrame(
        frame=Frame(
            scenario_id=scenario_id,
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase="current",
            agent_states=agents,
            traffic_lights=traffic_lights,
        ),
        visibility="current",
        available_modalities=frozenset({"agents", "valid_agents", "traffic_lights", "map"}),
    )


def context(scenario_id, frames, map_features=None):
    return AlignmentContext(
        scenario_id=scenario_id,
        watermark=Watermark(scenario_id, frames[-1].frame.step_index, frames[-1].frame.timestamp_seconds),
        observed_frames=tuple(frames[:-1]),
        current_frame=frames[-1],
        future_frames=(),
        input_frames=tuple(frames),
        source="unit",
        map_features=map_features or {},
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


def straight_lane(feature_id, y):
    return MapFeature(
        feature_id=feature_id,
        feature_type="lane",
        polyline=(Point3D(-20.0, y, 0.0), Point3D(0.0, y, 0.0), Point3D(20.0, y, 0.0)),
        polygon=(),
        properties={},
    )


class ClassicHighValueSemanticsV2ContractTests(unittest.TestCase):
    def test_classic_pack_declares_pair_ego_speed_gate_for_review_risk_rules(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rules = {
            rule.rule_id: rule
            for rule in RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules
            if getattr(rule, "condition", None) is not None and hasattr(rule.condition, "calls")
        }

        for rule_id in ("low_ttc_pair", "cut_in_lateral_approach", "same_path_overlap"):
            operators = [call.operator_name for call in rules[rule_id].condition.calls]
            self.assertIn("predicate.pair_ego_speed_above", operators)

        low_ttc = next(
            call for call in rules["low_ttc_pair"].condition.calls
            if call.operator_name == "predicate.low_ttc"
        )
        self.assertGreaterEqual(low_ttc.args.get("min_closing_speed_mps", 0.0), 1.0)

    def test_stationary_sdc_does_not_emit_cut_in_review_when_vehicle_passes_nearby(self):
        frames = (
            aligned_frame("stationary-cut-in", 0, (agent(1), agent(2, x=8.0, y=3.2, vx=3.0, vy=-12.0, heading=-0.2))),
            aligned_frame("stationary-cut-in", 1, (agent(1), agent(2, x=8.0, y=2.0, vx=3.0, vy=-12.0, heading=-0.2))),
            aligned_frame("stationary-cut-in", 2, (agent(1), agent(2, x=8.0, y=0.7, vx=3.0, vy=-12.0, heading=0.0))),
        )

        result = classic_engine().evaluate(context("stationary-cut-in", frames))
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertNotIn("cut_in_confirmed", review_tags)
        self.assertNotIn("cut_in_risk", review_tags)

    def test_stationary_sdc_does_not_emit_persistent_low_ttc_when_target_approaches(self):
        frames = (
            aligned_frame("stationary-low-ttc", 0, (agent(1), agent(2, x=10.0, vx=-5.0))),
            aligned_frame("stationary-low-ttc", 1, (agent(1), agent(2, x=9.5, vx=-5.0))),
            aligned_frame("stationary-low-ttc", 2, (agent(1), agent(2, x=9.0, vx=-5.0))),
        )

        result = classic_engine().evaluate(context("stationary-low-ttc", frames))
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertNotIn("persistent_low_ttc_pair", review_tags)

    def test_red_light_running_does_not_stitch_different_lane_stop_lines(self):
        lane_7_red = TrafficLightState(7, "stop", Point3D(0.0, 0.0, 0.0))
        lane_8_red = TrafficLightState(8, "stop", Point3D(0.0, 5.0, 0.0))
        frames = (
            aligned_frame(
                "mixed-lane-red-light",
                0,
                (agent(1, x=-3.0, y=0.1, vx=5.0),),
                (lane_7_red, lane_8_red),
            ),
            aligned_frame(
                "mixed-lane-red-light",
                1,
                (agent(1, x=2.0, y=5.1, vx=5.0),),
                (lane_7_red, lane_8_red),
            ),
        )

        result = classic_engine().evaluate(
            context(
                "mixed-lane-red-light",
                frames,
                map_features={7: straight_lane(7, 0.0), 8: straight_lane(8, 5.0)},
            )
        )
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertNotIn("red_light_running", review_tags)

    def test_sdc_stopped_tags_remain_out_of_review_events(self):
        frames = (
            aligned_frame("stopped-debug-only", 0, (agent(1, vx=0.1),)),
            aligned_frame("stopped-debug-only", 1, (agent(1, vx=0.1),)),
            aligned_frame("stopped-debug-only", 2, (agent(1, vx=0.1),)),
        )

        result = classic_engine().evaluate(context("stopped-debug-only", frames))
        review_tags = {event.tag_name for event in result.events if event.metadata.get("intent") == "review"}

        self.assertFalse(any(tag.startswith("sdc_vehicle_stopped") for tag in review_tags))


if __name__ == "__main__":
    unittest.main()
