import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D
from trigger_engine.rules.events import TagEvent


POLICY_RULE_YAML = """
rules:
  - id: noisy_vehicle
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.always_true_demo
    emit:
      tag: noisy_vehicle
      policy:
        cooldown_frames: 2
"""


TEMPORAL_POLICY_RULE_YAML = """
rules:
  - id: noisy_vehicle
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: predicate.always_true_demo
    emit:
      tag: noisy_vehicle
      policy:
        cooldown_frames: 10

  - id: noisy_vehicle_sustained
    kind: temporal
    subject: agent
    when:
      tag: noisy_vehicle
      sustained:
        frames: 3
    emit:
      tag: noisy_vehicle_sustained
"""


def event(frame_index, tag_name="noisy_vehicle", subject_id=1, rule_id="noisy_vehicle"):
    return TagEvent(
        scenario_id="scenario-policy",
        source="unit",
        frame_index=frame_index,
        timestamp_seconds=frame_index * 0.1,
        tag_name=tag_name,
        subject_type="agent",
        subject_id=subject_id,
        value=True,
        rule_id=rule_id,
        metadata={"rule_kind": "single_frame"},
    )


def event_for_scenario(scenario_id, frame_index, tag_name="noisy_vehicle", subject_id=1, rule_id="noisy_vehicle"):
    base = event(frame_index, tag_name=tag_name, subject_id=subject_id, rule_id=rule_id)
    from dataclasses import replace

    return replace(base, scenario_id=scenario_id)


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


def aligned_frame(step_index):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-policy",
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase="current" if step_index == 2 else "history",
            agent_states=(agent(1),),
            traffic_lights=(),
        ),
        visibility="current" if step_index == 2 else "observed",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def make_context():
    frames = (aligned_frame(0), aligned_frame(1), aligned_frame(2))
    return AlignmentContext(
        scenario_id="scenario-policy",
        watermark=Watermark("scenario-policy", 2, 0.2),
        observed_frames=frames[:2],
        current_frame=frames[2],
        future_frames=(),
        input_frames=frames,
        source="unit",
    )


class AlwaysTrueDemoOperator:
    name = "predicate.always_true_demo"
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
            True,
            {},
        )


class EventPolicyContractTests(unittest.TestCase):
    def test_rule_parser_reads_emit_cooldown_policy(self):
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(POLICY_RULE_YAML)

        self.assertEqual(rule_set.rules[0].emit.policy.cooldown_frames, 2)

    def test_rule_parser_rejects_invalid_policy_values(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        text = POLICY_RULE_YAML.replace("cooldown_frames: 2", "cooldown_frames: -1")

        with self.assertRaisesRegex(RuleParseError, "cooldown_frames"):
            RuleParser().parse_yaml(text)

        text = POLICY_RULE_YAML.replace("cooldown_frames: 2", "within_frames: 3")

        with self.assertRaisesRegex(RuleParseError, "within_frames"):
            RuleParser().parse_yaml(text)

    def test_event_policy_engine_applies_cooldown_by_tag_subject(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine
        from trigger_engine.rules.parser import RuleParser

        rules = RuleParser().parse_yaml(POLICY_RULE_YAML).rules
        filtered = EventPolicyEngine().apply(
            (
                event(0),
                event(1),
                event(2),
                event(3),
                event(1, subject_id=2),
            ),
            rules,
        )

        self.assertEqual(
            [(e.frame_index, e.subject_id) for e in filtered],
            [(0, 1), (3, 1), (1, 2)],
        )
        self.assertEqual(filtered[0].metadata["policy"]["cooldown_frames"], 2)
        self.assertEqual(filtered[0].metadata["policy"]["suppressed_until_frame_index"], 2)

    def test_event_policy_engine_preserves_raw_event_timestamp_for_replay(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine
        from trigger_engine.rules.parser import RuleParser

        rules = RuleParser().parse_yaml(POLICY_RULE_YAML).rules
        original = event(5)
        filtered = EventPolicyEngine().apply((original,), rules)

        self.assertEqual(filtered[0].frame_index, 5)
        self.assertEqual(filtered[0].timestamp_seconds, 0.5)
        self.assertEqual(filtered[0].metadata["policy"]["output_frame_index"], 5)
        self.assertEqual(filtered[0].metadata["policy"]["output_timestamp_seconds"], 0.5)
        self.assertEqual(original.metadata, {"rule_kind": "single_frame"})

    def test_event_policy_engine_leaves_events_without_policy_unchanged(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine
        from trigger_engine.rules.parser import RuleParser

        text = POLICY_RULE_YAML.replace(
            "      policy:\n        cooldown_frames: 2\n",
            "",
        )
        rules = RuleParser().parse_yaml(text).rules
        original = event(0)

        filtered = EventPolicyEngine().apply((original,), rules)

        self.assertEqual(filtered, (original,))
        self.assertIs(filtered[0], original)

    def test_event_policy_engine_cooldown_is_scoped_by_scenario(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine
        from trigger_engine.rules.parser import RuleParser

        rules = RuleParser().parse_yaml(POLICY_RULE_YAML).rules

        filtered = EventPolicyEngine().apply(
            (
                event_for_scenario("scenario-a", 0),
                event_for_scenario("scenario-b", 1),
            ),
            rules,
        )

        self.assertEqual([event.scenario_id for event in filtered], ["scenario-a", "scenario-b"])

    def test_trigger_engine_applies_emit_policy_after_temporal_detection(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        operators = OperatorRegistry()
        operators.register(AlwaysTrueDemoOperator())
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("policy", TEMPORAL_POLICY_RULE_YAML)
        rules.activate("policy")

        result = TriggerEngine(operators, rules).evaluate(make_context())
        events_by_tag = {}
        for tag_event in result.events:
            events_by_tag.setdefault(tag_event.tag_name, []).append(tag_event)

        self.assertEqual([event.frame_index for event in events_by_tag["noisy_vehicle"]], [0])
        self.assertIn("noisy_vehicle_sustained", events_by_tag)
        self.assertEqual(events_by_tag["noisy_vehicle_sustained"][0].frame_index, 2)
        self.assertEqual(result.stats.events_emitted, len(result.events))


if __name__ == "__main__":
    unittest.main()
