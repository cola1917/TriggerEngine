import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D
from trigger_engine.operators.builtins import AgentPairSubject


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


def aligned_frame(step_index, agents):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-cut-in-sequence",
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase="current" if step_index == 3 else "history",
            agent_states=agents,
            traffic_lights=(),
        ),
        visibility="current" if step_index == 3 else "observed",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def cut_in_context():
    ego_0 = agent(1, x=0.0, y=0.0, vx=10.0, vy=0.0, heading=0.0)
    ego_1 = agent(1, x=1.0, y=0.0, vx=10.0, vy=0.0, heading=0.0)
    ego_2 = agent(1, x=2.0, y=0.0, vx=10.0, vy=0.0, heading=0.0)
    ego_3 = agent(1, x=3.0, y=0.0, vx=10.0, vy=0.0, heading=0.0)

    other_0 = agent(2, x=8.0, y=3.2, vx=8.0, vy=-1.2, heading=-0.12)
    other_1 = agent(2, x=8.8, y=2.2, vx=8.0, vy=-1.2, heading=-0.12)
    other_2 = agent(2, x=9.6, y=0.7, vx=4.0, vy=0.0, heading=0.0)
    other_3 = agent(2, x=10.0, y=0.5, vx=4.0, vy=0.0, heading=0.0)

    frames = (
        aligned_frame(0, (ego_0, other_0)),
        aligned_frame(1, (ego_1, other_1)),
        aligned_frame(2, (ego_2, other_2)),
        aligned_frame(3, (ego_3, other_3)),
    )
    return AlignmentContext(
        scenario_id="scenario-cut-in-sequence",
        watermark=Watermark("scenario-cut-in-sequence", 3, 0.3),
        observed_frames=frames[:3],
        current_frame=frames[3],
        future_frames=(),
        input_frames=frames,
        source="unit",
        sdc_track_index=1,
        sdc_track_id=1,
    )


class CutInSequenceContractTests(unittest.TestCase):
    def test_builtin_cut_in_spatial_operators_are_registered(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.operators.builtins import register_builtin_operators

        registry = OperatorRegistry()
        register_builtin_operators(registry)

        self.assertEqual(
            registry.get("predicate.lateral_gap_between").subject_type,
            "agent_pair",
        )
        self.assertEqual(
            registry.get("predicate.same_path_overlap").subject_type,
            "agent_pair",
        )

    def test_lateral_gap_between_detects_adjacent_not_same_path_pair(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.operators.builtins import register_builtin_operators

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        op = registry.get("predicate.lateral_gap_between")
        ego = agent(1, x=0.0, y=0.0, vx=10.0)
        adjacent = agent(2, x=7.0, y=3.0, vx=8.0)
        same_path = agent(3, x=7.0, y=0.5, vx=8.0)
        frame = aligned_frame(0, (ego, adjacent, same_path))

        args = {
            "min_lateral_m": 1.5,
            "max_lateral_m": 4.5,
            "max_longitudinal_m": 15.0,
        }

        self.assertTrue(
            op.evaluate(None, frame, AgentPairSubject(ego, adjacent), args).value
        )
        self.assertFalse(
            op.evaluate(None, frame, AgentPairSubject(ego, same_path), args).value
        )

    def test_same_path_overlap_detects_front_corridor_not_adjacent_pair(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.operators.builtins import register_builtin_operators

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        op = registry.get("predicate.same_path_overlap")
        ego = agent(1, x=0.0, y=0.0, vx=10.0)
        same_path = agent(2, x=8.0, y=0.6, vx=4.0)
        adjacent = agent(3, x=8.0, y=3.0, vx=4.0)
        frame = aligned_frame(0, (ego, same_path, adjacent))

        args = {
            "max_lateral_m": 1.2,
            "min_longitudinal_m": 0.0,
            "max_longitudinal_m": 20.0,
        }

        self.assertTrue(
            op.evaluate(None, frame, AgentPairSubject(ego, same_path), args).value
        )
        self.assertFalse(
            op.evaluate(None, frame, AgentPairSubject(ego, adjacent), args).value
        )

    def test_cut_in_spatial_operators_ignore_invalid_pair_members(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.operators.builtins import register_builtin_operators

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        ego = agent(1, x=0.0, y=0.0, vx=10.0)
        invalid_other = agent(2, x=8.0, y=3.0, vx=8.0, valid=False)
        frame = aligned_frame(0, (ego, invalid_other))
        pair = AgentPairSubject(ego, invalid_other)

        self.assertFalse(
            registry.get("predicate.lateral_gap_between")
            .evaluate(
                None,
                frame,
                pair,
                {
                    "min_lateral_m": 1.5,
                    "max_lateral_m": 4.5,
                    "max_longitudinal_m": 15.0,
                },
            )
            .value
        )
        self.assertFalse(
            registry.get("predicate.same_path_overlap")
            .evaluate(
                None,
                frame,
                pair,
                {
                    "max_lateral_m": 4.0,
                    "min_longitudinal_m": 0.0,
                    "max_longitudinal_m": 20.0,
                },
            )
            .value
        )

    def test_classic_pack_defines_sequence_based_cut_in_rules(self):
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        self.assertIn("adjacent_vehicle", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("cut_in_lateral_approach", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("same_path_overlap", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("cut_in_confirmed", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("cut_in_risk", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("sequence:", CLASSIC_SCENARIO_RULES_YAML)
        self.assertIn("within_seconds:", CLASSIC_SCENARIO_RULES_YAML)
        self.assertNotIn("within_frames:", CLASSIC_SCENARIO_RULES_YAML)

    def test_classic_cut_in_lateral_approach_is_spatially_bounded(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rule_set = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML)
        rule = next(rule for rule in rule_set.rules if rule.rule_id == "cut_in_lateral_approach")
        operator_names = [call.operator_name for call in rule.condition.calls]

        self.assertEqual(
            operator_names,
                [
                    "predicate.pair_types_are",
                    "predicate.pair_ego_speed_above",
                    "predicate.pair_other_speed_above",
                    "predicate.lateral_gap_between",
                    "predicate.lateral_motion_toward",
                    "predicate.heading_converging",
            ],
        )

    def test_classic_cut_in_lateral_approach_requires_near_aligned_heading(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import register_classic_scenario_pack

        ego_0 = agent(1, x=0.0, y=0.0, vx=3.0, heading=0.0)
        ego_1 = agent(1, x=0.3, y=0.0, vx=3.0, heading=0.0)
        ego_2 = agent(1, x=0.6, y=0.0, vx=3.0, heading=0.0)
        target_0 = agent(2, x=8.0, y=3.0, vx=0.0, vy=-3.0, heading=-1.57)
        target_1 = agent(2, x=8.0, y=1.8, vx=0.0, vy=-3.0, heading=-1.57)
        target_2 = agent(2, x=8.0, y=0.6, vx=0.0, vy=-3.0, heading=-1.57)
        frames = (
            aligned_frame(0, (ego_0, target_0)),
            aligned_frame(1, (ego_1, target_1)),
            aligned_frame(2, (ego_2, target_2)),
        )
        context = AlignmentContext(
            scenario_id="scenario-crossing-not-cut-in",
            watermark=Watermark("scenario-crossing-not-cut-in", 2, 0.2),
            observed_frames=frames[:2],
            current_frame=frames[2],
            future_frames=(),
            input_frames=frames,
            source="unit",
            sdc_track_index=1,
            sdc_track_id=1,
        )

        operators = OperatorRegistry()
        rules = RuleRegistry(operator_registry=operators)
        register_classic_scenario_pack(operators, rules)

        result = TriggerEngine(operators, rules).evaluate(context)
        tags = {event.tag_name for event in result.events if event.subject_id == "1:2"}

        self.assertIn("adjacent_vehicle", tags)
        self.assertNotIn("cut_in_lateral_approach", tags)
        self.assertNotIn("cut_in_confirmed", tags)
        self.assertNotIn("cut_in_risk", tags)

    def test_classic_pack_emits_cut_in_sequence_tags(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import register_classic_scenario_pack

        operators = OperatorRegistry()
        rules = RuleRegistry(operator_registry=operators)
        register_classic_scenario_pack(operators, rules)

        result = TriggerEngine(operators, rules).evaluate(cut_in_context())
        events = [event for event in result.events if event.subject_id == "1:2"]
        tags = {event.tag_name for event in events}

        self.assertIn("adjacent_vehicle", tags)
        self.assertIn("cut_in_lateral_approach", tags)
        self.assertIn("same_path_overlap", tags)
        self.assertIn("low_ttc_pair", tags)
        self.assertIn("cut_in_risk", tags)
        self.assertNotIn("cut_in_confirmed", tags)

        risk_event = next(e for e in events if e.tag_name == "cut_in_risk")
        self.assertEqual(risk_event.metadata["temporal_kind"], "sequence")
        self.assertEqual(risk_event.subject_type, "sdc_pair")

    def test_classic_pair_rules_do_not_require_unbounded_pair_cache(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import register_classic_scenario_pack

        operators = OperatorRegistry()
        rules = RuleRegistry(operator_registry=operators)
        register_classic_scenario_pack(operators, rules)
        cache = SubjectCache()

        TriggerEngine(operators, rules, subject_cache=cache).evaluate(cut_in_context())

        for frame in cut_in_context().input_frames:
            self.assertEqual(cache.build_count("agent_pair", frame.frame.step_index), 0)


if __name__ == "__main__":
    unittest.main()
