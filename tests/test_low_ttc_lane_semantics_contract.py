from __future__ import annotations

import unittest

from tests.test_builtin_operators_contract import agent, aligned_frame
from trigger_engine.alignment.context import AlignmentContext, Watermark
from trigger_engine.data.frames import MapFeature, Point3D


def context_with_map(frame, map_features):
    return AlignmentContext(
        scenario_id="scenario-low-ttc-lane",
        watermark=Watermark("scenario-low-ttc-lane", 0, 0.0),
        observed_frames=(),
        current_frame=frame,
        future_frames=(),
        input_frames=(frame,),
        source="unit",
        map_features=map_features,
    )


def lane(feature_id: int, y: float) -> MapFeature:
    return MapFeature(
        feature_id=feature_id,
        feature_type="lane",
        polyline=(Point3D(-20.0, y, 0.0), Point3D(80.0, y, 0.0)),
        polygon=(),
        properties={"lane_type": "driving"},
    )


class LowTtcLaneSemanticsContractTests(unittest.TestCase):
    def test_same_lane_or_path_operator_is_registered(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)

        self.assertIn("predicate.same_lane_or_path", set(registry.names()))
        self.assertEqual(
            registry.get("predicate.same_lane_or_path").subject_type,
            "agent_pair",
        )

    def test_same_lane_pair_passes_and_adjacent_lane_pair_fails(self):
        from trigger_engine.operators.builtins import AgentPairSubject, register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        ego = agent(1, x=0.0, y=0.1, vx=10.0, heading=0.0)
        same_lane_target = agent(2, x=12.0, y=-0.1, vx=5.0, heading=0.0)
        adjacent_lane_target = agent(3, x=12.0, y=3.6, vx=5.0, heading=0.0)
        frame = aligned_frame(ego, same_lane_target, adjacent_lane_target)
        ctx = context_with_map(frame, {10: lane(10, 0.0), 11: lane(11, 3.6)})
        op = registry.get("predicate.same_lane_or_path")

        same_result = op.evaluate(
            ctx,
            frame,
            AgentPairSubject(ego=ego, other=same_lane_target),
            {"max_lane_lateral_m": 1.8, "max_heading_delta_rad": 0.7},
        )
        adjacent_result = op.evaluate(
            ctx,
            frame,
            AgentPairSubject(ego=ego, other=adjacent_lane_target),
            {"max_lane_lateral_m": 1.8, "max_heading_delta_rad": 0.7},
        )

        self.assertTrue(same_result.value)
        self.assertEqual(same_result.metadata["mode"], "lane")
        self.assertEqual(same_result.metadata["ego_lane_id"], 10)
        self.assertFalse(adjacent_result.value)
        self.assertEqual(adjacent_result.metadata["ego_lane_id"], 10)
        self.assertEqual(adjacent_result.metadata["other_lane_id"], 11)

    def test_no_map_strict_same_path_fallback_can_pass(self):
        from trigger_engine.operators.builtins import AgentPairSubject, register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        ego = agent(1, x=0.0, y=0.0, vx=10.0, heading=0.0)
        target = agent(2, x=12.0, y=0.8, vx=5.0, heading=0.05)
        frame = aligned_frame(ego, target)
        ctx = context_with_map(frame, {})

        result = registry.get("predicate.same_lane_or_path").evaluate(
            ctx,
            frame,
            AgentPairSubject(ego=ego, other=target),
            {
                "fallback_max_lateral_m": 1.2,
                "fallback_max_heading_delta_rad": 0.35,
                "allow_fallback_without_map": True,
            },
        )

        self.assertTrue(result.value)
        self.assertEqual(result.metadata["mode"], "fallback_path")

    def test_classic_low_ttc_rule_requires_same_lane_or_path_gate(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rules = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules
        low_ttc = next(rule for rule in rules if rule.rule_id == "low_ttc_pair")
        operator_names = [call.operator_name for call in low_ttc.condition.calls]

        self.assertIn("predicate.same_lane_or_path", operator_names)

        pair_in_front = next(
            call for call in low_ttc.condition.calls
            if call.operator_name == "predicate.pair_in_front"
        )
        low_ttc_call = next(
            call for call in low_ttc.condition.calls
            if call.operator_name == "predicate.low_ttc"
        )
        self.assertLessEqual(pair_in_front.args["max_lateral_m"], 2.0)
        self.assertLessEqual(low_ttc_call.args["max_lateral_m"], 2.0)
        self.assertLessEqual(low_ttc_call.args["max_longitudinal_m"], 60.0)


if __name__ == "__main__":
    unittest.main()
