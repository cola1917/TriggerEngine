import unittest

from tests.test_performance_v1_contract import aligned_frame, agent
from trigger_engine.alignment.context import AlignmentContext, Watermark


GATED_SEQUENCE_YAML = """
rules:
  - id: start_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.start_pair
    emit:
      tag: start_pair

  - id: middle_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.middle_pair
    emit:
      tag: middle_pair

  - id: end_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.end_pair
    emit:
      tag: end_pair

  - id: pair_sequence
    kind: temporal
    subject: agent_pair
    when:
      sequence:
        - tag: start_pair
        - tag: middle_pair
        - tag: end_pair
      within_frames: 3
    emit:
      tag: pair_sequence
"""


SUSTAINED_SOURCE_YAML = """
rules:
  - id: start_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.start_pair
    emit:
      tag: start_pair

  - id: middle_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.middle_pair
    emit:
      tag: middle_pair

  - id: pair_sequence
    kind: temporal
    subject: agent_pair
    when:
      sequence:
        - tag: start_pair
        - tag: middle_pair
      within_frames: 3
    emit:
      tag: pair_sequence

  - id: middle_sustained
    kind: temporal
    subject: agent_pair
    when:
      tag: middle_pair
      sustained:
        frames: 2
    emit:
      tag: middle_sustained
"""


AGENT_SEQUENCE_YAML = """
rules:
  - id: agent_start
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.agent_start
    emit:
      tag: agent_start

  - id: agent_end
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.agent_end
    emit:
      tag: agent_end

  - id: agent_sequence
    kind: temporal
    subject: agent
    when:
      sequence:
        - tag: agent_start
        - tag: agent_end
      within_frames: 3
    emit:
      tag: agent_sequence
"""


def make_context(agent_count=8, frame_count=3):
    frames = tuple(
        aligned_frame(i, tuple(agent(track_id) for track_id in range(agent_count)))
        for i in range(frame_count)
    )
    return AlignmentContext(
        scenario_id="scenario-sequence-gating",
        watermark=Watermark(
            "scenario-sequence-gating",
            frames[-1].frame.step_index,
            frames[-1].frame.timestamp_seconds,
        ),
        observed_frames=frames[:-1],
        current_frame=frames[-1],
        future_frames=(),
        input_frames=frames,
        source="unit",
    )


class StartPairOperator:
    name = "predicate.start_pair"
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
            subject.subject_id == "0:1" and frame.frame.step_index == 0,
            {},
        )


class CountingMiddleOperator:
    name = "predicate.middle_pair"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def __init__(self):
        self.calls = []

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        self.calls.append((frame.frame.step_index, subject.subject_id))
        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            True,
            {},
        )


class EndPairOperator:
    name = "predicate.end_pair"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def __init__(self):
        self.calls = []

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        self.calls.append((frame.frame.step_index, subject.subject_id))
        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.subject_id == "0:1" and frame.frame.step_index == 2,
            {},
        )


class AgentStartOperator:
    name = "predicate.agent_start"
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
            subject.track_id == 0 and frame.frame.step_index == 0,
            {},
        )


class CountingAgentEndOperator:
    name = "predicate.agent_end"
    result_kind = "predicate"
    subject_type = "agent"

    def __init__(self):
        self.calls = []

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        self.calls.append((frame.frame.step_index, subject.track_id))
        return OperatorResult(
            self.name,
            "agent",
            subject.track_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.track_id == 0 and frame.frame.step_index == 2,
            {},
        )


class SequenceCandidateGatingContractTests(unittest.TestCase):
    def test_sequence_middle_steps_are_evaluated_only_for_prior_subject_candidates(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        middle = CountingMiddleOperator()
        end = EndPairOperator()
        operators = OperatorRegistry()
        operators.register(StartPairOperator())
        operators.register(middle)
        operators.register(end)
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("gated", GATED_SEQUENCE_YAML)
        rules.activate("gated")

        result = TriggerEngine(operators, rules).evaluate(make_context())

        self.assertEqual({event.tag_name for event in result.events}, {
            "start_pair",
            "middle_pair",
            "end_pair",
            "pair_sequence",
        })
        self.assertEqual(middle.calls, [(0, "0:1"), (1, "0:1"), (2, "0:1")])
        self.assertEqual(end.calls, [(0, "0:1"), (1, "0:1"), (2, "0:1")])
        self.assertEqual(
            [
                diagnostic.metadata["rule_id"]
                for diagnostic in result.diagnostics
                if diagnostic.message == "sequence_candidate_gating"
            ],
            ["middle_pair", "end_pair"],
        )

    def test_sustained_source_tags_are_not_gated(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        middle = CountingMiddleOperator()
        operators = OperatorRegistry()
        operators.register(StartPairOperator())
        operators.register(middle)
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("not-gated", SUSTAINED_SOURCE_YAML)
        rules.activate("not-gated")

        result = TriggerEngine(operators, rules).evaluate(make_context(agent_count=4))

        self.assertEqual(len(middle.calls), 4 * 3 * 3)
        self.assertNotIn(
            "middle_pair",
            {
                diagnostic.metadata["rule_id"]
                for diagnostic in result.diagnostics
                if diagnostic.message == "sequence_candidate_gating"
            },
        )

    def test_non_pair_sequences_are_not_gated(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        end = CountingAgentEndOperator()
        operators = OperatorRegistry()
        operators.register(AgentStartOperator())
        operators.register(end)
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("agent-sequence", AGENT_SEQUENCE_YAML)
        rules.activate("agent-sequence")

        result = TriggerEngine(operators, rules).evaluate(make_context(agent_count=4))

        self.assertIn("agent_sequence", {event.tag_name for event in result.events})
        self.assertEqual(len(end.calls), 4 * 3)
        self.assertFalse([
            diagnostic
            for diagnostic in result.diagnostics
            if diagnostic.message == "sequence_candidate_gating"
        ])


if __name__ == "__main__":
    unittest.main()
