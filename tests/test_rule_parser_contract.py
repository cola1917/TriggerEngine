import unittest
from dataclasses import is_dataclass


VALID_RULE_YAML = """
rules:
  - id: vehicle_stopped
    description: Vehicle speed is below threshold.
    subject: agent
    window:
      history_steps: 3
    when:
      all:
        - operator: predicate.type_is
          args:
            object_type: vehicle
        - operator: predicate.speed_below
          args:
            threshold_mps: 0.5
          for_last_n_frames: 3
    emit:
      tag: vehicle_stopped
      value: true
      metadata:
        severity: info
"""


class RuleParserContractTests(unittest.TestCase):
    def test_rule_ast_and_tag_event_are_dataclasses(self):
        from trigger_engine.rules.ast import AllCondition, OperatorCall, Rule, RuleEmit, RuleSet, RuleWindow
        from trigger_engine.rules.events import TagEvent

        for cls in (AllCondition, OperatorCall, Rule, RuleEmit, RuleSet, RuleWindow, TagEvent):
            self.assertTrue(is_dataclass(cls), f"{cls.__name__} must be a dataclass")

    def test_parser_converts_yaml_to_rule_set_ast(self):
        from trigger_engine.rules.ast import AllCondition
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(VALID_RULE_YAML)

        self.assertEqual(len(rule_set.rules), 1)
        rule = rule_set.rules[0]
        self.assertEqual(rule.rule_id, "vehicle_stopped")
        self.assertEqual(rule.description, "Vehicle speed is below threshold.")
        self.assertEqual(rule.subject_type, "agent")
        self.assertEqual(rule.window.history_steps, 3)
        self.assertIsInstance(rule.condition, AllCondition)
        self.assertEqual(rule.condition.calls[0].operator_name, "predicate.type_is")
        self.assertEqual(rule.condition.calls[0].args, {"object_type": "vehicle"})
        self.assertEqual(rule.condition.calls[1].for_last_n_frames, 3)
        self.assertEqual(rule.emit.tag_name, "vehicle_stopped")
        self.assertTrue(rule.emit.value)
        self.assertEqual(rule.emit.metadata, {"severity": "info"})

    def test_parser_rejects_duplicate_rule_ids(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        text = """
rules:
  - id: duplicate
    subject: frame
    when:
      all:
        - operator: predicate.a
    emit:
      tag: duplicate
  - id: duplicate
    subject: frame
    when:
      all:
        - operator: predicate.b
    emit:
      tag: duplicate
"""

        with self.assertRaisesRegex(RuleParseError, "duplicate"):
            RuleParser().parse_yaml(text)

    def test_parser_rejects_invalid_subject(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        text = """
rules:
  - id: invalid_subject
    subject: object
    when:
      all:
        - operator: predicate.a
    emit:
      tag: invalid_subject
"""

        with self.assertRaisesRegex(RuleParseError, "subject"):
            RuleParser().parse_yaml(text)

    def test_parser_rejects_unknown_condition_shape(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        text = """
rules:
  - id: bad_condition
    subject: frame
    when:
      any:
        - operator: predicate.a
    emit:
      tag: bad_condition
"""

        with self.assertRaisesRegex(RuleParseError, "when.all"):
            RuleParser().parse_yaml(text)


if __name__ == "__main__":
    unittest.main()
