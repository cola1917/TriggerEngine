import unittest

from trigger_engine.rules.events import TagEvent


def event(
    frame_index,
    tag_name="supporting_signal",
    intent="supporting",
    subject_id=1,
    rule_id=None,
):
    rule_id = rule_id or tag_name
    return TagEvent(
        scenario_id="scenario-compact",
        source="unit",
        frame_index=frame_index,
        timestamp_seconds=frame_index * 0.1,
        tag_name=tag_name,
        subject_type="agent",
        subject_id=subject_id,
        value=True,
        rule_id=rule_id,
        metadata={"intent": intent, "rule_kind": "single_frame"},
    )


COMPACT_RULE_YAML = """
rules:
  - id: supporting_signal
    subject: agent
    when:
      all:
        - operator: predicate.always_true_demo
    emit:
      tag: supporting_signal
      intent: supporting
      policy:
        compact:
          by: subject
          mode: interval
"""


REVIEW_COMPACT_RULE_YAML = COMPACT_RULE_YAML.replace(
    "intent: supporting",
    "intent: review",
)


MIXED_SAME_TAG_POLICY_YAML = """
rules:
  - id: compact_rule
    subject: agent
    when:
      all:
        - operator: predicate.always_true_demo
    emit:
      tag: shared_signal
      intent: supporting
      policy:
        compact:
          by: subject
          mode: interval

  - id: raw_rule
    subject: agent
    when:
      all:
        - operator: predicate.always_true_demo
    emit:
      tag: shared_signal
      intent: supporting
"""


class EventCompactionContractTests(unittest.TestCase):
    def test_rule_parser_reads_emit_compaction_policy(self):
        from trigger_engine.rules.parser import RuleParser

        rule = RuleParser().parse_yaml(COMPACT_RULE_YAML).rules[0]

        self.assertEqual(rule.emit.policy.compact.by, "subject")
        self.assertEqual(rule.emit.policy.compact.mode, "interval")

    def test_rule_parser_rejects_compaction_policy_on_review_intent(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        with self.assertRaisesRegex(RuleParseError, "review"):
            RuleParser().parse_yaml(REVIEW_COMPACT_RULE_YAML)

    def test_event_policy_engine_compacts_consecutive_supporting_events_by_subject(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine
        from trigger_engine.rules.parser import RuleParser

        rules = RuleParser().parse_yaml(COMPACT_RULE_YAML).rules

        compacted = EventPolicyEngine().apply(
            (
                event(0),
                event(1),
                event(2),
                event(4),
                event(5),
                event(1, subject_id=2),
            ),
            rules,
        )

        self.assertEqual(
            [(item.frame_index, item.subject_id) for item in compacted],
            [(0, 1), (4, 1), (1, 2)],
        )

        first = compacted[0].metadata["compaction"]
        self.assertEqual(first["mode"], "interval")
        self.assertEqual(first["by"], "subject")
        self.assertEqual(first["start_frame_index"], 0)
        self.assertEqual(first["end_frame_index"], 2)
        self.assertEqual(first["start_timestamp_seconds"], 0.0)
        self.assertEqual(first["end_timestamp_seconds"], 0.2)
        self.assertEqual(first["frame_count"], 3)
        self.assertEqual(first["raw_frame_indices"], (0, 1, 2))
        self.assertEqual(first["raw_timestamps_seconds"], (0.0, 0.1, 0.2))

    def test_event_policy_engine_does_not_compact_review_events(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine

        compacted = EventPolicyEngine().apply(
            (event(0, intent="review"), event(1, intent="review")),
            (),
        )

        self.assertEqual([item.frame_index for item in compacted], [0, 1])

    def test_event_compaction_policy_is_scoped_by_rule_not_only_tag_name(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine
        from trigger_engine.rules.parser import RuleParser

        rules = RuleParser().parse_yaml(MIXED_SAME_TAG_POLICY_YAML).rules

        compacted = EventPolicyEngine().apply(
            (
                event(0, tag_name="shared_signal", rule_id="compact_rule"),
                event(1, tag_name="shared_signal", rule_id="compact_rule"),
                event(0, tag_name="shared_signal", subject_id=2, rule_id="raw_rule"),
                event(1, tag_name="shared_signal", subject_id=2, rule_id="raw_rule"),
            ),
            rules,
        )

        compact_events = [item for item in compacted if item.rule_id == "compact_rule"]
        raw_events = [item for item in compacted if item.rule_id == "raw_rule"]

        self.assertEqual(len(compact_events), 1)
        self.assertIn("compaction", compact_events[0].metadata)
        self.assertEqual([item.frame_index for item in raw_events], [0, 1])
        self.assertNotIn("compaction", raw_events[0].metadata)


if __name__ == "__main__":
    unittest.main()
