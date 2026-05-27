import unittest

from tests.test_rule_compiler_contract import registry_with_vehicle_ops
from tests.test_rule_dsl_temporal_contract import RULE_YAML

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D


def agent(track_id, speed):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(0.0, 0.0, 0.0),
        velocity_x=speed,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def aligned_frame(step_index, visibility, agents):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-core",
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase=visibility,
            agent_states=agents,
            traffic_lights=(),
        ),
        visibility=visibility,
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def make_context():
    f0 = aligned_frame(0, "observed", (agent(100, 0.1),))
    f1 = aligned_frame(1, "observed", (agent(100, 0.2),))
    f2 = aligned_frame(2, "current", (agent(100, 0.3),))
    future = aligned_frame(3, "future", (agent(300, 0.1),))
    return AlignmentContext(
        scenario_id="scenario-core",
        watermark=Watermark("scenario-core", 2, 0.2),
        observed_frames=(f0, f1),
        current_frame=f2,
        future_frames=(future,),
        input_frames=(f0, f1, f2),
        source="file-001",
    )


class TypeIsOperator:
    name = "predicate.type_is"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            self.name,
            "agent",
            subject.track_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.object_type == args["object_type"],
            {},
        )


class SpeedBelowOperator:
    name = "predicate.speed_below"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            self.name,
            "agent",
            subject.track_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.velocity_x < args["threshold_mps"],
            {},
        )


def runtime_registry():
    registry = registry_with_vehicle_ops()
    registry._operators = {}
    registry.register(TypeIsOperator())
    registry.register(SpeedBelowOperator())
    return registry


class TriggerEngineContractTests(unittest.TestCase):
    def build_engine(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine

        operators = runtime_registry()
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("default", RULE_YAML)
        rules.activate("default")
        return TriggerEngine(operator_registry=operators, rule_registry=rules)

    def build_profiled_engine(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine

        operators = runtime_registry()
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("default", RULE_YAML)
        rules.activate("default")
        return TriggerEngine(operator_registry=operators, rule_registry=rules, profile_rules=True)

    def test_trigger_engine_evaluate_accepts_alignment_context_only(self):
        engine = self.build_engine()

        with self.assertRaises(TypeError):
            engine.evaluate(make_context(), RULE_YAML)

    def test_trigger_engine_outputs_single_frame_and_temporal_tag_events(self):
        engine = self.build_engine()

        result = engine.evaluate(make_context())

        self.assertEqual(result.scenario_id, "scenario-core")
        self.assertEqual(result.source, "file-001")
        self.assertEqual(result.plan_id, "default")
        self.assertEqual(
            [(event.tag_name, event.frame_index, event.subject_id) for event in result.events],
            [
                ("vehicle_stopped", 0, 100),
                ("vehicle_stopped", 1, 100),
                ("vehicle_stopped", 2, 100),
                ("vehicle_stopped_for_3_frames", 2, 100),
            ],
        )
        self.assertEqual(result.events[-1].metadata["rule_kind"], "temporal")
        self.assertEqual(result.events[-1].metadata["supporting_frame_indices"], (0, 1, 2))
        self.assertEqual(result.events[0].metadata["rule_kind"], "single_frame")

    def test_trigger_engine_stats_and_future_boundary(self):
        engine = self.build_engine()

        result = engine.evaluate(make_context())

        self.assertEqual(result.stats.input_frames, 3)
        self.assertEqual(result.stats.future_frames, 1)
        self.assertEqual(result.stats.single_frame_rules, 1)
        self.assertEqual(result.stats.temporal_rules, 1)
        self.assertEqual(result.stats.events_emitted, 4)
        self.assertNotIn(3, [event.frame_index for event in result.events])
        self.assertNotIn(300, [event.subject_id for event in result.events])

    def test_trigger_engine_requires_active_plan(self):
        from trigger_engine.engine.registry import RuleRegistry, RuleRegistryError
        from trigger_engine.engine.trigger_engine import TriggerEngine

        operators = runtime_registry()
        rules = RuleRegistry(operator_registry=operators)
        engine = TriggerEngine(operator_registry=operators, rule_registry=rules)

        with self.assertRaisesRegex(RuleRegistryError, "active"):
            engine.evaluate(make_context())

    def test_trigger_engine_can_emit_rule_profile_diagnostics(self):
        engine = self.build_profiled_engine()

        result = engine.evaluate(make_context())

        profiles = [
            diagnostic.metadata
            for diagnostic in result.diagnostics
            if diagnostic.message == "rule_profile"
        ]
        self.assertEqual([profile["rule_id"] for profile in profiles], ["vehicle_stopped", "vehicle_stopped_for_3_frames"])
        self.assertEqual(profiles[0]["rule_kind"], "single_frame")
        self.assertEqual(profiles[0]["frames_evaluated"], 3)
        self.assertEqual(profiles[0]["events_emitted"], 3)
        self.assertGreaterEqual(profiles[0]["seconds"], 0.0)
        self.assertEqual(profiles[1]["rule_kind"], "temporal")
        self.assertEqual(profiles[1]["events_emitted"], 1)


if __name__ == "__main__":
    unittest.main()
