import unittest

from trigger_engine.rules.events import TagEvent


EPISODE_RULE_YAML = """
rules:
  - id: low_ttc_pair
    subject: agent_pair
    when:
      all:
        - operator: predicate.agent_pair_always_true
    emit:
      tag: low_ttc_pair
      intent: supporting

  - id: persistent_low_ttc_pair
    kind: temporal
    subject: agent_pair
    when:
      tag: low_ttc_pair
      sustained:
        frames: 3
    emit:
      tag: persistent_low_ttc_pair
      intent: review
      policy:
        episode:
          by: subject
          mode: interval
"""


BAD_SUPPORTING_EPISODE_YAML = EPISODE_RULE_YAML.replace(
    "intent: review",
    "intent: supporting",
)


def review_event(frame_index, support):
    return TagEvent(
        scenario_id="scenario-review-episode",
        source="unit",
        frame_index=frame_index,
        timestamp_seconds=frame_index * 0.1,
        tag_name="persistent_low_ttc_pair",
        subject_type="agent_pair",
        subject_id="1:2",
        value=True,
        rule_id="persistent_low_ttc_pair",
        metadata={
            "intent": "review",
            "rule_kind": "temporal",
            "temporal_kind": "sustained",
            "source_tag": "low_ttc_pair",
            "supporting_frame_indices": tuple(support),
            "supporting_timestamps_seconds": tuple(i * 0.1 for i in support),
        },
    )


class ReviewEpisodeContractTests(unittest.TestCase):
    def test_parser_reads_review_episode_policy(self):
        from trigger_engine.rules.parser import RuleParser

        rules = RuleParser().parse_yaml(EPISODE_RULE_YAML).rules
        persistent = rules[1]

        self.assertEqual(persistent.emit.policy.episode.by, "subject")
        self.assertEqual(persistent.emit.policy.episode.mode, "interval")

    def test_parser_rejects_episode_policy_on_non_review_intent(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        with self.assertRaisesRegex(RuleParseError, "review"):
            RuleParser().parse_yaml(BAD_SUPPORTING_EPISODE_YAML)

    def test_episode_policy_merges_sliding_temporal_review_events(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine
        from trigger_engine.rules.parser import RuleParser

        rules = RuleParser().parse_yaml(EPISODE_RULE_YAML).rules
        merged = EventPolicyEngine().apply(
            (
                review_event(2, (0, 1, 2)),
                review_event(3, (1, 2, 3)),
                review_event(4, (2, 3, 4)),
                review_event(6, (4, 5, 6)),
            ),
            rules,
        )

        self.assertEqual([event.frame_index for event in merged], [2, 6])
        first = merged[0].metadata["episode"]
        self.assertEqual(first["mode"], "interval")
        self.assertEqual(first["by"], "subject")
        self.assertEqual(first["start_frame_index"], 2)
        self.assertEqual(first["end_frame_index"], 4)
        self.assertEqual(first["event_count"], 3)
        self.assertEqual(first["raw_event_frame_indices"], (2, 3, 4))
        self.assertEqual(first["supporting_frame_indices"], (0, 1, 2, 3, 4))
        self.assertEqual(first["supporting_timestamps_seconds"], (0.0, 0.1, 0.2, 0.3, 0.4))

    def test_classic_low_ttc_uses_supporting_then_review_episode(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rules = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules
        by_id = {rule.rule_id: rule for rule in rules}

        self.assertEqual(by_id["low_ttc_pair"].emit.intent, "supporting")
        self.assertEqual(by_id["persistent_low_ttc_pair"].emit.intent, "review")
        self.assertEqual(by_id["persistent_low_ttc_pair"].emit.policy.episode.mode, "interval")


if __name__ == "__main__":
    unittest.main()
