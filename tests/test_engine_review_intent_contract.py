import unittest

from tests.test_rule_engine_contract import (
    FutureLeakDetectorOperator,
    SpeedBelowOperator,
    TypeIsOperator,
    make_context as make_rule_context,
)
from tests.test_temporal_sequence_contract import (
    AdjacentDemoOperator,
    SamePathDemoOperator,
    make_context as make_sequence_context,
)


class EngineReviewIntentContractTests(unittest.TestCase):
    def build_agent_registry(self):
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        registry.register(TypeIsOperator())
        registry.register(SpeedBelowOperator())
        registry.register(FutureLeakDetectorOperator())
        return registry

    def test_parser_accepts_emit_intent_and_defaults_to_debug(self):
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: review_rule
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
    emit:
      tag: high_value_event
      intent: review

  - id: default_rule
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
    emit:
      tag: intermediate_signal
"""
        )

        self.assertEqual(rule_set.rules[0].emit.intent, "review")
        self.assertEqual(rule_set.rules[1].emit.intent, "debug")

    def test_parser_rejects_unknown_emit_intent(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        with self.assertRaisesRegex(RuleParseError, "intent"):
            RuleParser().parse_yaml(
                """
rules:
  - id: bad_intent
    subject: agent
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
    emit:
      tag: bad
      intent: dashboard
"""
            )

    def test_single_frame_engine_copies_intent_into_tag_event_metadata(self):
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
    emit:
      tag: vehicle_stopped
      intent: supporting
      metadata:
        family: stopped
"""
        )

        registry = self.build_agent_registry()
        events = RuleEngine(registry).evaluate(rule_set, make_rule_context())

        self.assertGreater(len(events), 0)
        self.assertEqual(events[0].metadata["intent"], "supporting")
        self.assertEqual(events[0].metadata["family"], "stopped")
        self.assertEqual(events[0].metadata["rule_kind"], "single_frame")

    def test_temporal_engine_copies_intent_into_tag_event_metadata(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry

        yaml_text = """
rules:
  - id: adjacent_vehicle
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.adjacent_demo
    emit:
      tag: adjacent_vehicle
      intent: supporting

  - id: same_path_overlap
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.same_path_demo
    emit:
      tag: same_path_overlap
      intent: supporting

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
      intent: review
      metadata:
        family: cut_in
"""
        operators = OperatorRegistry()
        operators.register(AdjacentDemoOperator())
        operators.register(SamePathDemoOperator())
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("intent_sequence", yaml_text)
        rules.activate("intent_sequence")

        result = TriggerEngine(operators, rules).evaluate(make_sequence_context())
        review_events = [event for event in result.events if event.tag_name == "cut_in_confirmed"]

        self.assertEqual(len(review_events), 1)
        self.assertEqual(review_events[0].metadata["intent"], "review")
        self.assertEqual(review_events[0].metadata["family"], "cut_in")
        self.assertEqual(review_events[0].metadata["rule_kind"], "temporal")

    def test_viewer_export_prefers_event_metadata_intent_over_tag_name_fallback(self):
        from tests.test_review_viewer_v2_contract import make_context_with_future_and_map
        from trigger_engine.engine.trigger_engine import EngineResult, EngineStats
        from trigger_engine.rules.events import TagEvent
        from tools.export_viewer import build_viewer_payload

        result = EngineResult(
            scenario_id="scenario-review-v2",
            source="unit",
            plan_id="intent-plan",
            events=(
                TagEvent(
                    "scenario-review-v2",
                    "unit",
                    1,
                    0.1,
                    "vehicle_stopped_for_3_frames",
                    "agent",
                    1,
                    True,
                    "stopped_debug",
                    {"intent": "review"},
                ),
                TagEvent(
                    "scenario-review-v2",
                    "unit",
                    2,
                    0.2,
                    "cut_in_confirmed",
                    "agent_pair",
                    "1:2",
                    True,
                    "cut_in_debug_override",
                    {"intent": "debug"},
                ),
            ),
            stats=EngineStats(3, 0, 1, 1, 2),
            diagnostics=(),
        )

        payload = build_viewer_payload(make_context_with_future_and_map(), result)

        self.assertEqual(payload["review_event_indices"], [0])
        self.assertEqual(payload["event_groups"]["primary"], [0])
        self.assertEqual(payload["event_groups"]["debug"], [1])


if __name__ == "__main__":
    unittest.main()
