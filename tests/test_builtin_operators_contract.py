import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D, TrafficLightState


def agent(track_id, x=0.0, y=0.0, vx=0.0, vy=0.0, heading=0.0, object_type="vehicle", valid=True):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type=object_type,
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


def aligned_frame(*agents, traffic_lights=()):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-builtins",
            step_index=0,
            timestamp_seconds=0.0,
            phase="current",
            agent_states=agents,
            traffic_lights=traffic_lights,
        ),
        visibility="current",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def context(frame):
    return AlignmentContext(
        scenario_id="scenario-builtins",
        watermark=Watermark("scenario-builtins", 0, 0.0),
        observed_frames=(),
        current_frame=frame,
        future_frames=(),
        input_frames=(frame,),
        source="unit",
    )


class BuiltinOperatorsContractTests(unittest.TestCase):
    def test_register_builtin_operators_registers_expected_names(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        register_builtin_operators(registry)

        self.assertEqual(
            set(registry.names()),
            {
                "predicate.type_is",
                "predicate.speed_below",
                "predicate.speed_above",
                "predicate.pair_types_are",
                "predicate.pair_in_front",
                "predicate.low_ttc",
                "predicate.close_lateral_gap",
                "predicate.lateral_gap_between",
                "predicate.lateral_motion_toward",
                "predicate.heading_converging",
                "predicate.same_path_overlap",
                "predicate.near_red_light_stop_point",
                "predicate.red_light_before_stop_line",
                "predicate.red_light_after_stop_line",
            },
        )

    def test_speed_and_type_operators(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        frame = aligned_frame(agent(1, vx=0.2, object_type="vehicle"))
        subject = frame.frame.agent_states[0]

        self.assertTrue(registry.get("predicate.type_is").evaluate(context(frame), frame, subject, {"object_type": "vehicle"}).value)
        self.assertTrue(registry.get("predicate.speed_below").evaluate(context(frame), frame, subject, {"threshold_mps": 0.5}).value)
        self.assertFalse(registry.get("predicate.speed_above").evaluate(context(frame), frame, subject, {"threshold_mps": 0.5}).value)

    def test_speed_operators_ignore_invalid_agent_states(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        frame = aligned_frame(agent(1, vx=0.0, valid=False))
        subject = frame.frame.agent_states[0]

        self.assertFalse(
            registry.get("predicate.speed_below")
            .evaluate(context(frame), frame, subject, {"threshold_mps": 0.5})
            .value
        )
        self.assertFalse(
            registry.get("predicate.speed_above")
            .evaluate(context(frame), frame, subject, {"threshold_mps": 0.5})
            .value
        )

    def test_pair_low_ttc_operator(self):
        from trigger_engine.operators.builtins import AgentPairSubject, register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        ego = agent(1, x=0.0, y=0.0, vx=10.0, heading=0.0)
        other = agent(2, x=10.0, y=0.0, vx=5.0, heading=0.0)
        frame = aligned_frame(ego, other)
        pair = AgentPairSubject(ego=ego, other=other)

        self.assertTrue(registry.get("predicate.pair_in_front").evaluate(context(frame), frame, pair, {"max_lateral_m": 2.0}).value)
        result = registry.get("predicate.low_ttc").evaluate(context(frame), frame, pair, {"threshold_s": 3.0})
        self.assertTrue(result.value)
        self.assertAlmostEqual(result.metadata["ttc_s"], 2.0)

    def test_low_ttc_is_false_when_other_agent_is_behind_or_not_closing(self):
        from trigger_engine.operators.builtins import AgentPairSubject, register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        ego = agent(1, x=0.0, y=0.0, vx=5.0, heading=0.0)
        behind = agent(2, x=-10.0, y=0.0, vx=0.0, heading=0.0)
        faster_front = agent(3, x=10.0, y=0.0, vx=8.0, heading=0.0)
        frame = aligned_frame(ego, behind, faster_front)

        self.assertFalse(
            registry.get("predicate.low_ttc")
            .evaluate(context(frame), frame, AgentPairSubject(ego=ego, other=behind), {"threshold_s": 3.0})
            .value
        )
        self.assertFalse(
            registry.get("predicate.low_ttc")
            .evaluate(context(frame), frame, AgentPairSubject(ego=ego, other=faster_front), {"threshold_s": 3.0})
            .value
        )

    def test_register_builtin_operators_only_suppresses_duplicate_registration(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        class BrokenRegistry(OperatorRegistry):
            def register(self, operator):
                if operator.name == "predicate.type_is":
                    raise RuntimeError("boom")
                return super().register(operator)

        with self.assertRaisesRegex(RuntimeError, "boom"):
            register_builtin_operators(BrokenRegistry())

    def test_cut_in_candidate_operators(self):
        from trigger_engine.operators.builtins import AgentPairSubject, register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        ego = agent(1, x=0.0, y=0.0, vx=8.0, vy=0.0, heading=0.0)
        other = agent(2, x=5.0, y=2.0, vx=8.0, vy=-1.0, heading=-0.2)
        frame = aligned_frame(ego, other)
        pair = AgentPairSubject(ego=ego, other=other)

        self.assertTrue(registry.get("predicate.close_lateral_gap").evaluate(context(frame), frame, pair, {"max_lateral_m": 3.0, "max_longitudinal_m": 10.0}).value)
        self.assertTrue(registry.get("predicate.lateral_motion_toward").evaluate(context(frame), frame, pair, {"min_lateral_speed_mps": 0.2}).value)
        self.assertTrue(registry.get("predicate.heading_converging").evaluate(context(frame), frame, pair, {"min_heading_delta_rad": 0.05, "max_heading_delta_rad": 0.5}).value)

    def test_near_red_light_stop_point_operator(self):
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        register_builtin_operators(registry)
        light = TrafficLightState(lane_id=7, state="stop", stop_point=Point3D(1.0, 0.0, 0.0))
        frame = aligned_frame(agent(1, x=1.2, y=0.0), traffic_lights=(light,))
        subject = frame.frame.agent_states[0]

        result = registry.get("predicate.near_red_light_stop_point").evaluate(
            context(frame), frame, subject, {"max_distance_m": 1.0}
        )

        self.assertTrue(result.value)
        self.assertEqual(result.metadata["lane_id"], 7)


if __name__ == "__main__":
    unittest.main()
