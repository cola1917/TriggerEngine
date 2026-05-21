import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D, ScenarioBundle


def agent(track_id, object_type="vehicle", speed=0.0, valid=True):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type=object_type,
        timestamp_seconds=track_id * 0.1,
        center=Point3D(float(track_id), 0.0, 0.0),
        velocity_x=speed,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=valid,
    )


def aligned_frame(step_index, visibility, agents=()):
    frame = Frame(
        scenario_id="scenario-rules",
        step_index=step_index,
        timestamp_seconds=step_index * 0.1,
        phase="current" if visibility == "current" else visibility,
        agent_states=agents,
        traffic_lights=(),
    )
    return AlignedFrame(
        frame=frame,
        visibility=visibility,
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def make_context():
    observed = aligned_frame(0, "observed", (agent(100, speed=0.1),))
    current = aligned_frame(1, "current", (agent(100, speed=0.2), agent(200, "pedestrian", 0.1)))
    future = aligned_frame(2, "future", (agent(300, speed=0.0),))
    return AlignmentContext(
        scenario_id="scenario-rules",
        watermark=Watermark("scenario-rules", 1, 0.1),
        observed_frames=(observed,),
        current_frame=current,
        future_frames=(future,),
        input_frames=(observed, current),
    )


class TypeIsOperator:
    name = "predicate.type_is"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            operator_name=self.name,
            subject_type="agent",
            subject_id=subject.track_id,
            frame_index=frame.frame.step_index,
            timestamp_seconds=frame.frame.timestamp_seconds,
            value=subject.object_type == args["object_type"],
            metadata={"object_type": args["object_type"]},
        )


class SpeedBelowOperator:
    name = "predicate.speed_below"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        speed = (subject.velocity_x**2 + subject.velocity_y**2) ** 0.5
        return OperatorResult(
            operator_name=self.name,
            subject_type="agent",
            subject_id=subject.track_id,
            frame_index=frame.frame.step_index,
            timestamp_seconds=frame.frame.timestamp_seconds,
            value=speed < args["threshold_mps"],
            metadata={"speed_mps": speed, "threshold_mps": args["threshold_mps"]},
        )


class FutureLeakDetectorOperator:
    name = "predicate.no_future_seen"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        future_ids = {agent.track_id for item in context.future_frames for agent in item.frame.agent_states}
        value = subject.track_id not in future_ids and frame.frame.step_index <= context.watermark.step_index
        return OperatorResult(
            operator_name=self.name,
            subject_type="agent",
            subject_id=subject.track_id,
            frame_index=frame.frame.step_index,
            timestamp_seconds=frame.frame.timestamp_seconds,
            value=value,
            metadata={},
        )


class RuleEngineContractTests(unittest.TestCase):
    def build_registry(self):
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        registry.register(TypeIsOperator())
        registry.register(SpeedBelowOperator())
        registry.register(FutureLeakDetectorOperator())
        return registry

    def test_rule_engine_emits_tag_events_for_matching_agent_subjects(self):
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: vehicle_stopped
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.speed_below
          args:
            threshold_mps: 0.5
    emit:
      tag: vehicle_stopped
      value: true
"""
        )

        events = RuleEngine(self.build_registry()).evaluate(rule_set, make_context())

        self.assertEqual([(event.frame_index, event.subject_id) for event in events], [(0, 100), (1, 100)])
        self.assertEqual(events[0].scenario_id, "scenario-rules")
        self.assertIsNone(events[0].source)
        self.assertEqual(events[0].tag_name, "vehicle_stopped")
        self.assertEqual(events[0].subject_type, "agent")
        self.assertEqual(events[0].rule_id, "vehicle_stopped")
        self.assertTrue(events[0].value)
        self.assertIn("operator_results", events[0].metadata)

    def test_rule_engine_uses_only_alignment_input_frames(self):
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: no_future_leak
    subject: agent
    when:
      all:
        - operator: predicate.no_future_seen
    emit:
      tag: no_future_leak
"""
        )

        events = RuleEngine(self.build_registry()).evaluate(rule_set, make_context())

        self.assertEqual([event.frame_index for event in events], [0, 1, 1])
        self.assertNotIn(2, [event.frame_index for event in events])
        self.assertNotIn(300, [event.subject_id for event in events])

    def test_rule_engine_reports_missing_operator(self):
        from trigger_engine.operators.registry import OperatorRegistryError
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: missing_operator
    subject: agent
    when:
      all:
        - operator: predicate.missing
    emit:
      tag: missing_operator
"""
        )

        with self.assertRaisesRegex(OperatorRegistryError, "predicate.missing"):
            RuleEngine(self.build_registry()).evaluate(rule_set, make_context())

    def test_rule_engine_carries_alignment_source_into_tag_events(self):
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        context = make_context()
        context = AlignmentContext(
            scenario_id=context.scenario_id,
            watermark=context.watermark,
            observed_frames=context.observed_frames,
            current_frame=context.current_frame,
            future_frames=context.future_frames,
            input_frames=context.input_frames,
            source="file-001",
        )
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: no_future_leak
    subject: agent
    when:
      all:
        - operator: predicate.no_future_seen
    emit:
      tag: no_future_leak
"""
        )

        events = RuleEngine(self.build_registry()).evaluate(rule_set, context)

        self.assertEqual(events[0].source, "file-001")

    def test_rule_engine_rejects_operator_subject_mismatch(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine, RuleEngineError
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        operator = FutureLeakDetectorOperator()
        operator.subject_type = "frame"
        registry.register(operator)
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: mismatched_subject
    subject: agent
    when:
      all:
        - operator: predicate.no_future_seen
    emit:
      tag: mismatched_subject
"""
        )

        with self.assertRaisesRegex(RuleEngineError, "subject_type"):
            RuleEngine(registry).evaluate(rule_set, make_context())

    def test_rule_engine_rejects_non_bool_predicate_result(self):
        from trigger_engine.operators.base import OperatorResult
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine, RuleEngineError
        from trigger_engine.rules.parser import RuleParser

        class BadPredicate:
            name = "predicate.bad"
            result_kind = "predicate"
            subject_type = "agent"

            def evaluate(self, context, frame, subject, args):
                return OperatorResult(
                    operator_name=self.name,
                    subject_type="agent",
                    subject_id=subject.track_id,
                    frame_index=frame.frame.step_index,
                    timestamp_seconds=frame.frame.timestamp_seconds,
                    value=1.0,
                    metadata={},
                )

        registry = OperatorRegistry()
        registry.register(BadPredicate())
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: bad_predicate
    subject: agent
    when:
      all:
        - operator: predicate.bad
    emit:
      tag: bad_predicate
"""
        )

        with self.assertRaisesRegex(RuleEngineError, "predicate"):
            RuleEngine(registry).evaluate(rule_set, make_context())


if __name__ == "__main__":
    unittest.main()
