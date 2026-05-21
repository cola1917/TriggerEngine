import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D


SEQUENCE_RULE_YAML = """
rules:
  - id: adjacent_vehicle
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.adjacent_demo
    emit:
      tag: adjacent_vehicle

  - id: same_path_overlap
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.same_path_demo
    emit:
      tag: same_path_overlap

  - id: cut_in_confirmed
    kind: temporal
    subject: agent_pair
    when:
      sequence:
        - tag: adjacent_vehicle
        - tag: same_path_overlap
      within_frames: 3
    emit:
      tag: cut_in_confirmed
"""


def agent(track_id):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(0.0, 0.0, 0.0),
        velocity_x=0.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def aligned_frame(step_index):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-sequence",
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase="current" if step_index == 2 else "history",
            agent_states=(agent(1), agent(2)),
            traffic_lights=(),
        ),
        visibility="current" if step_index == 2 else "observed",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def make_context():
    frames = (aligned_frame(0), aligned_frame(1), aligned_frame(2))
    return AlignmentContext(
        scenario_id="scenario-sequence",
        watermark=Watermark("scenario-sequence", 2, 0.2),
        observed_frames=frames[:2],
        current_frame=frames[2],
        future_frames=(),
        input_frames=frames,
        source="unit",
    )


class AdjacentDemoOperator:
    name = "predicate.adjacent_demo"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.subject_id == "1:2" and frame.frame.step_index == 0,
            {},
        )


class SamePathDemoOperator:
    name = "predicate.same_path_demo"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.subject_id == "1:2" and frame.frame.step_index == 2,
            {},
        )


class TemporalSequenceContractTests(unittest.TestCase):
    def test_parser_supports_sequence_temporal_condition(self):
        from trigger_engine.rules.ast import SequenceTagCondition
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(SEQUENCE_RULE_YAML)
        condition = rule_set.rules[2].condition

        self.assertIsInstance(condition, SequenceTagCondition)
        self.assertEqual([step.tag_name for step in condition.steps], ["adjacent_vehicle", "same_path_overlap"])
        self.assertEqual(condition.within_frames, 3)

    def test_compiler_rejects_sequence_with_unknown_source_tag(self):
        from trigger_engine.engine.compiler import RuleCompileError, RuleCompiler
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.parser import RuleParser

        text = SEQUENCE_RULE_YAML.replace(
            "        - tag: same_path_overlap",
            "        - tag: missing_tag",
        )
        registry = OperatorRegistry()
        registry.register(AdjacentDemoOperator())
        registry.register(SamePathDemoOperator())

        with self.assertRaisesRegex(RuleCompileError, "missing_tag"):
            RuleCompiler().compile("sequence", RuleParser().parse_yaml(text), registry)

    def test_tag_timeline_matches_sequence_by_subject_and_window(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline
        from trigger_engine.rules.events import TagEvent

        events = (
            TagEvent("s", None, 0, 0.0, "adjacent_vehicle", "agent_pair", "1:2", True, "r1", {}),
            TagEvent("s", None, 2, 0.2, "same_path_overlap", "agent_pair", "1:2", True, "r2", {}),
            TagEvent("s", None, 2, 0.2, "same_path_overlap", "agent_pair", "2:1", True, "r2", {}),
        )
        timeline = TagTimeline.from_events(events)

        ok, support = timeline.sequence(
            (
                TagKey("adjacent_vehicle", "agent_pair", "1:2"),
                TagKey("same_path_overlap", "agent_pair", "1:2"),
            ),
            end_frame_index=2,
            within_frames=3,
        )
        wrong_subject, _ = timeline.sequence(
            (
                TagKey("adjacent_vehicle", "agent_pair", "2:1"),
                TagKey("same_path_overlap", "agent_pair", "2:1"),
            ),
            end_frame_index=2,
            within_frames=3,
        )

        self.assertTrue(ok)
        self.assertEqual(support, (0, 2))
        self.assertFalse(wrong_subject)

    def test_trigger_engine_emits_sequence_temporal_event(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        operators = OperatorRegistry()
        operators.register(AdjacentDemoOperator())
        operators.register(SamePathDemoOperator())
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("sequence", SEQUENCE_RULE_YAML)
        rules.activate("sequence")

        result = TriggerEngine(operators, rules).evaluate(make_context())
        events = [event for event in result.events if event.tag_name == "cut_in_confirmed"]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].subject_id, "1:2")
        self.assertEqual(events[0].frame_index, 2)
        self.assertEqual(events[0].metadata["temporal_kind"], "sequence")
        self.assertEqual(events[0].metadata["supporting_frame_indices"], (0, 2))


if __name__ == "__main__":
    unittest.main()
