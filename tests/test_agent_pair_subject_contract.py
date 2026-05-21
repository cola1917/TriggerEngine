import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D


def agent(track_id, x=0.0, y=0.0, object_type="vehicle"):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type=object_type,
        timestamp_seconds=0.0,
        center=Point3D(x, y, 0.0),
        velocity_x=0.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def context_with_agents(*agents):
    frame = AlignedFrame(
        frame=Frame(
            scenario_id="scenario-pair",
            step_index=0,
            timestamp_seconds=0.0,
            phase="current",
            agent_states=agents,
            traffic_lights=(),
        ),
        visibility="current",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )
    return AlignmentContext(
        scenario_id="scenario-pair",
        watermark=Watermark("scenario-pair", 0, 0.0),
        observed_frames=(),
        current_frame=frame,
        future_frames=(),
        input_frames=(frame,),
        source="unit",
    )


class AlwaysPairTrueOperator:
    name = "predicate.agent_pair_always_true"
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
            True,
            {"ego": subject.ego.track_id, "other": subject.other.track_id},
        )


class AgentPairSubjectContractTests(unittest.TestCase):
    def test_rule_parser_accepts_agent_pair_subject(self):
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: pair_rule
    subject: agent_pair
    when:
      all:
        - operator: predicate.agent_pair_always_true
    emit:
      tag: pair_rule
"""
        )

        self.assertEqual(rule_set.rules[0].subject_type, "agent_pair")

    def test_rule_engine_generates_ordered_agent_pair_subjects(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysPairTrueOperator())
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: pair_rule
    subject: agent_pair
    when:
      all:
        - operator: predicate.agent_pair_always_true
    emit:
      tag: pair_rule
"""
        )

        events = RuleEngine(registry).evaluate(
            rule_set, context_with_agents(agent(1), agent(2), agent(3))
        )

        self.assertEqual(
            [event.subject_id for event in events],
            ["1:2", "1:3", "2:1", "2:3", "3:1", "3:2"],
        )
        self.assertNotIn("1:1", [event.subject_id for event in events])


if __name__ == "__main__":
    unittest.main()
