import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D
from trigger_engine.rules.events import TagEvent


TEMPORAL_V2_YAML = """
rules:
  - id: moving_source
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.moving_demo
    emit:
      tag: moving_source

  - id: stopped_for_seconds
    kind: temporal
    subject: agent
    when:
      tag: moving_source
      sustained:
        seconds: 0.2
    emit:
      tag: moving_for_0_2s

  - id: approach_source
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.approach_demo
    emit:
      tag: approach_source

  - id: crossed_source
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.crossed_demo
    emit:
      tag: crossed_source

  - id: crossed_within_seconds
    kind: temporal
    subject: agent
    when:
      sequence:
        - tag: approach_source
        - tag: crossed_source
      within_seconds: 0.25
      max_gap_frames: 2
    emit:
      tag: crossed_within_0_25s
"""


def agent(track_id=1):
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


def aligned_frame(step_index, timestamp_seconds):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-temporal-v2",
            step_index=step_index,
            timestamp_seconds=timestamp_seconds,
            phase="current" if step_index == 3 else "history",
            agent_states=(agent(1),),
            traffic_lights=(),
        ),
        visibility="current" if step_index == 3 else "observed",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def make_context():
    frames = (
        aligned_frame(0, 0.0),
        aligned_frame(1, 0.1),
        aligned_frame(2, 0.2),
        aligned_frame(3, 0.3),
    )
    return AlignmentContext(
        scenario_id="scenario-temporal-v2",
        watermark=Watermark("scenario-temporal-v2", 3, 0.3),
        observed_frames=frames[:3],
        current_frame=frames[3],
        future_frames=(),
        input_frames=frames,
        source="unit",
    )


class MovingDemoOperator:
    name = "predicate.moving_demo"
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
            frame.frame.step_index in {0, 1, 2},
            {},
        )


class ApproachDemoOperator:
    name = "predicate.approach_demo"
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
            frame.frame.step_index == 1,
            {},
        )


class CrossedDemoOperator:
    name = "predicate.crossed_demo"
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
            frame.frame.step_index == 3,
            {},
        )


class TemporalRuleV2ContractTests(unittest.TestCase):
    def test_parser_supports_seconds_windows_and_gap(self):
        from trigger_engine.rules.ast import SequenceTagCondition, SustainedTagCondition
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(TEMPORAL_V2_YAML)
        sustained = rule_set.rules[1].condition
        sequence = rule_set.rules[4].condition

        self.assertIsInstance(sustained, SustainedTagCondition)
        self.assertIsNone(sustained.frames)
        self.assertEqual(sustained.seconds, 0.2)
        self.assertIsInstance(sequence, SequenceTagCondition)
        self.assertIsNone(sequence.within_frames)
        self.assertEqual(sequence.within_seconds, 0.25)
        self.assertEqual(sequence.max_gap_frames, 2)

    def test_parser_rejects_ambiguous_time_windows(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        sustained_text = """
rules:
  - id: ambiguous_sustained
    kind: temporal
    subject: agent
    when:
      tag: moving_source
      sustained:
        frames: 3
        seconds: 0.2
    emit:
      tag: ambiguous_sustained
"""
        sequence_text = """
rules:
  - id: ambiguous_sequence
    kind: temporal
    subject: agent
    when:
      sequence:
        - tag: approach_source
        - tag: crossed_source
      within_frames: 4
      within_seconds: 0.25
    emit:
      tag: ambiguous_sequence
"""

        with self.assertRaisesRegex(RuleParseError, "sustained"):
            RuleParser().parse_yaml(sustained_text)
        with self.assertRaisesRegex(RuleParseError, "within"):
            RuleParser().parse_yaml(sequence_text)

    def test_tag_timeline_matches_sustained_seconds(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline

        timeline = TagTimeline.from_events(
            (
                TagEvent("s", None, 0, 0.0, "moving_source", "agent", 1, True, "r", {}),
                TagEvent("s", None, 1, 0.1, "moving_source", "agent", 1, True, "r", {}),
                TagEvent("s", None, 2, 0.2, "moving_source", "agent", 1, True, "r", {}),
            )
        )

        ok, support = timeline.sustained_seconds(
            TagKey("moving_source", "agent", 1),
            end_frame_index=2,
            seconds=0.2,
        )

        self.assertTrue(ok)
        self.assertEqual(support, (0, 1, 2))
        self.assertEqual(timeline.timestamp_at(2), 0.2)

    def test_tag_timeline_matches_sequence_seconds_with_max_gap(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline

        timeline = TagTimeline.from_events(
            (
                TagEvent("s", None, 1, 0.1, "approach_source", "agent", 1, True, "r1", {}),
                TagEvent("s", None, 3, 0.3, "crossed_source", "agent", 1, True, "r2", {}),
            )
        )

        ok, support = timeline.sequence_seconds(
            (
                TagKey("approach_source", "agent", 1),
                TagKey("crossed_source", "agent", 1),
            ),
            end_frame_index=3,
            within_seconds=0.25,
            max_gap_frames=1,
        )
        too_tight, _ = timeline.sequence_seconds(
            (
                TagKey("approach_source", "agent", 1),
                TagKey("crossed_source", "agent", 1),
            ),
            end_frame_index=3,
            within_seconds=0.15,
            max_gap_frames=1,
        )
        too_much_gap, _ = timeline.sequence_seconds(
            (
                TagKey("approach_source", "agent", 1),
                TagKey("crossed_source", "agent", 1),
            ),
            end_frame_index=3,
            within_seconds=0.25,
            max_gap_frames=0,
        )

        self.assertTrue(ok)
        self.assertEqual(support, (1, 3))
        self.assertFalse(too_tight)
        self.assertFalse(too_much_gap)

    def test_tag_timeline_sequence_seconds_is_anchored_to_end_frame_time(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline

        timeline = TagTimeline.from_events(
            (
                TagEvent("s", None, 1, 0.1, "approach_source", "agent", 1, True, "r1", {}),
                TagEvent("s", None, 3, 0.3, "crossed_source", "agent", 1, True, "r2", {}),
                TagEvent("s", None, 10, 1.0, "unrelated", "agent", 1, True, "r3", {}),
            )
        )

        stale_match, _ = timeline.sequence_seconds(
            (
                TagKey("approach_source", "agent", 1),
                TagKey("crossed_source", "agent", 1),
            ),
            end_frame_index=10,
            within_seconds=0.25,
            max_gap_frames=2,
        )

        self.assertFalse(stale_match)

    def test_trigger_engine_emits_sustained_seconds_event_with_timestamp_metadata(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        operators = OperatorRegistry()
        operators.register(MovingDemoOperator())
        operators.register(ApproachDemoOperator())
        operators.register(CrossedDemoOperator())
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("temporal-v2", TEMPORAL_V2_YAML)
        rules.activate("temporal-v2")

        result = TriggerEngine(operators, rules).evaluate(make_context())
        events = [event for event in result.events if event.tag_name == "moving_for_0_2s"]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].frame_index, 2)
        self.assertEqual(events[0].metadata["temporal_kind"], "sustained")
        self.assertEqual(events[0].metadata["sustained_seconds"], 0.2)
        self.assertEqual(events[0].metadata["supporting_frame_indices"], (0, 1, 2))
        self.assertEqual(events[0].metadata["supporting_timestamps_seconds"], (0.0, 0.1, 0.2))
        self.assertEqual(events[0].metadata["first_matched_frame_index"], 0)
        self.assertEqual(events[0].metadata["last_matched_frame_index"], 2)
        self.assertEqual(events[0].metadata["first_matched_timestamp_seconds"], 0.0)
        self.assertEqual(events[0].metadata["last_matched_timestamp_seconds"], 0.2)

    def test_trigger_engine_emits_sequence_seconds_event_with_timestamp_metadata(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        operators = OperatorRegistry()
        operators.register(MovingDemoOperator())
        operators.register(ApproachDemoOperator())
        operators.register(CrossedDemoOperator())
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("temporal-v2", TEMPORAL_V2_YAML)
        rules.activate("temporal-v2")

        result = TriggerEngine(operators, rules).evaluate(make_context())
        events = [event for event in result.events if event.tag_name == "crossed_within_0_25s"]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].frame_index, 3)
        self.assertEqual(events[0].metadata["temporal_kind"], "sequence")
        self.assertEqual(events[0].metadata["within_seconds"], 0.25)
        self.assertEqual(events[0].metadata["max_gap_frames"], 2)
        self.assertEqual(events[0].metadata["supporting_frame_indices"], (1, 3))
        self.assertEqual(events[0].metadata["supporting_timestamps_seconds"], (0.1, 0.3))
        self.assertEqual(events[0].metadata["first_matched_frame_index"], 1)
        self.assertEqual(events[0].metadata["last_matched_frame_index"], 3)
        self.assertEqual(events[0].metadata["first_matched_timestamp_seconds"], 0.1)
        self.assertEqual(events[0].metadata["last_matched_timestamp_seconds"], 0.3)


if __name__ == "__main__":
    unittest.main()
