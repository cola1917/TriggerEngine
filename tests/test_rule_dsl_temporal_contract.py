import unittest
from dataclasses import is_dataclass


RULE_YAML = """
version: 1
rules:
  - id: vehicle_stopped
    kind: single_frame
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

  - id: vehicle_stopped_for_3_frames
    kind: temporal
    subject: agent
    when:
      tag: vehicle_stopped
      sustained:
        frames: 3
    emit:
      tag: vehicle_stopped_for_3_frames
"""


class RuleDslTemporalContractTests(unittest.TestCase):
    def test_temporal_condition_is_dataclass(self):
        from trigger_engine.rules.ast import SustainedTagCondition

        self.assertTrue(is_dataclass(SustainedTagCondition))

    def test_parser_supports_single_frame_and_temporal_rules(self):
        from trigger_engine.rules.ast import AllCondition, SustainedTagCondition
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(RULE_YAML)

        self.assertEqual(len(rule_set.rules), 2)
        single = rule_set.rules[0]
        temporal = rule_set.rules[1]

        self.assertEqual(single.kind, "single_frame")
        self.assertIsInstance(single.condition, AllCondition)
        self.assertEqual(single.emit.tag_name, "vehicle_stopped")

        self.assertEqual(temporal.kind, "temporal")
        self.assertIsInstance(temporal.condition, SustainedTagCondition)
        self.assertEqual(temporal.condition.tag_name, "vehicle_stopped")
        self.assertEqual(temporal.condition.frames, 3)
        self.assertEqual(temporal.emit.tag_name, "vehicle_stopped_for_3_frames")

    def test_parser_defaults_missing_kind_to_single_frame(self):
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: old_style_rule
    subject: frame
    when:
      all:
        - operator: predicate.has_lidar
    emit:
      tag: old_style_rule
"""
        )

        self.assertEqual(rule_set.rules[0].kind, "single_frame")

    def test_parser_rejects_operator_inside_temporal_rule(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        text = """
rules:
  - id: bad_temporal
    kind: temporal
    subject: agent
    when:
      all:
        - operator: predicate.speed_below
    emit:
      tag: bad_temporal
"""

        with self.assertRaisesRegex(RuleParseError, "temporal"):
            RuleParser().parse_yaml(text)


if __name__ == "__main__":
    unittest.main()
