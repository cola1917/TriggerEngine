import unittest
from dataclasses import is_dataclass


VALID_RULE_YAML = """
rules:
  - id: vehicle_stopped
    description: Vehicle speed is below threshold.
    subject: agent
    required_modalities: [agents, valid_agents]
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
        self.assertEqual(rule.required_modalities, frozenset({"agents", "valid_agents"}))
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

    def test_parser_rejects_invalid_required_modalities(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        text = """
rules:
  - id: invalid_modalities
    subject: frame
    required_modalities: traffic_lights
    when:
      all:
        - operator: predicate.a
    emit:
      tag: invalid_modalities
"""

        with self.assertRaisesRegex(RuleParseError, "required_modalities"):
            RuleParser().parse_yaml(text)

    def test_parser_records_deprecation_diagnostics_for_frame_based_rule_fields(self):
        from trigger_engine.rules.parser import RuleParser

        text = """
rules:
  - id: old_windowed_source
    subject: agent
    when:
      all:
        - operator: predicate.speed_below
          for_last_n_frames: 3
    emit:
      tag: old_windowed_source
  - id: old_sustained
    kind: temporal
    subject: agent
    when:
      tag: old_windowed_source
      sustained:
        frames: 3
    emit:
      tag: old_sustained
  - id: old_sequence
    kind: temporal
    subject: agent
    when:
      sequence:
        - tag: old_windowed_source
        - tag: old_sustained
      within_frames: 4
    emit:
      tag: old_sequence
"""

        rule_set = RuleParser().parse_yaml(text)

        deprecated_fields = [item.field_path for item in rule_set.diagnostics]
        self.assertEqual(
            deprecated_fields,
            [
                "rules[0].when.all[0].for_last_n_frames",
                "rules[1].when.sustained.frames",
                "rules[2].when.within_frames",
            ],
        )
        self.assertTrue(all(item.level == "warning" for item in rule_set.diagnostics))
        self.assertTrue(all(item.code == "deprecated_frame_window" for item in rule_set.diagnostics))


if __name__ == "__main__":
    unittest.main()
