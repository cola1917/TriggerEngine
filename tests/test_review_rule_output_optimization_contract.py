import unittest

from trigger_engine.rules.ast import EventPolicy, ReviewEpisodePolicy, Rule, RuleEmit, SustainedTagCondition
from trigger_engine.rules.events import TagEvent


def event(tag, frame, priority, *, subject="1:2", family="cut_in", start=None, end=None):
    metadata = {
        "intent": "review",
        "review_family": family,
        "review_priority": priority,
    }
    if start is not None and end is not None:
        metadata["episode"] = {
            "mode": "interval",
            "by": "subject",
            "start_frame_index": start,
            "end_frame_index": end,
        }
    return TagEvent(
        scenario_id="scenario-review-optimization",
        source="unit",
        frame_index=frame,
        timestamp_seconds=frame * 0.1,
        tag_name=tag,
        subject_type="sdc_pair",
        subject_id=subject,
        value=True,
        rule_id=tag,
        metadata=metadata,
    )


def episode_rule(tag):
    return Rule(
        rule_id=tag,
        kind="single_frame",
        subject_type="sdc_agent",
        condition=SustainedTagCondition(tag_name=tag, frames=1),
        emit=RuleEmit(
            tag_name=tag,
            intent="review",
            policy=EventPolicy(episode=ReviewEpisodePolicy(by="subject", mode="interval")),
        ),
    )


class ReviewRuleOutputOptimizationContractTests(unittest.TestCase):
    def test_event_policy_keeps_higher_priority_overlapping_review_family_event(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine

        confirmed = event("cut_in_confirmed", 5, 10, start=3, end=5)
        risk = event("cut_in_risk", 5, 20, start=3, end=5)

        filtered = EventPolicyEngine().apply((confirmed, risk), ())

        self.assertEqual([event.tag_name for event in filtered], ["cut_in_risk"])

    def test_event_policy_keeps_lower_priority_when_review_family_does_not_overlap(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine

        confirmed = event("cut_in_confirmed", 5, 10, start=1, end=2)
        risk = event("cut_in_risk", 9, 20, start=8, end=9)

        filtered = EventPolicyEngine().apply((confirmed, risk), ())

        self.assertEqual(
            {event.tag_name for event in filtered},
            {"cut_in_confirmed", "cut_in_risk"},
        )

    def test_event_policy_keeps_lower_priority_for_different_subjects(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine

        confirmed = event("cut_in_confirmed", 5, 10, subject="1:2", start=3, end=5)
        risk = event("cut_in_risk", 5, 20, subject="1:3", start=3, end=5)

        filtered = EventPolicyEngine().apply((confirmed, risk), ())

        self.assertEqual(
            {event.subject_id for event in filtered},
            {"1:2", "1:3"},
        )

    def test_classic_cut_in_rules_declare_review_family_priority(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        by_id = {
            rule.rule_id: rule
            for rule in RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules
        }

        self.assertEqual(by_id["cut_in_confirmed"].emit.metadata["review_family"], "cut_in")
        self.assertEqual(by_id["cut_in_confirmed"].emit.metadata["review_priority"], 10)
        self.assertEqual(by_id["cut_in_risk"].emit.metadata["review_family"], "cut_in")
        self.assertEqual(by_id["cut_in_risk"].emit.metadata["review_priority"], 20)

    def test_classic_repeated_lane_change_uses_episode_policy(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        by_id = {
            rule.rule_id: rule
            for rule in RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules
        }

        rule = by_id["sdc_repeated_lane_change"]
        self.assertEqual(rule.emit.intent, "review")
        self.assertEqual(rule.emit.policy.episode.mode, "interval")

    def test_episode_policy_compacts_repeated_lane_change_review_events(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine

        events = tuple(
            TagEvent(
                scenario_id="scenario-review-optimization",
                source="unit",
                frame_index=i,
                timestamp_seconds=i * 0.1,
                tag_name="sdc_repeated_lane_change",
                subject_type="sdc_agent",
                subject_id=1,
                value=True,
                rule_id="sdc_repeated_lane_change",
                metadata={"intent": "review"},
            )
            for i in range(11)
        )

        filtered = EventPolicyEngine().apply(events, (episode_rule("sdc_repeated_lane_change"),))

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].tag_name, "sdc_repeated_lane_change")
        self.assertEqual(filtered[0].metadata["episode"]["event_count"], 11)

    def test_classic_repeated_lane_change_uses_cooldown_for_separated_windows(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        by_id = {
            rule.rule_id: rule
            for rule in RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules
        }

        rule = by_id["sdc_repeated_lane_change"]
        self.assertGreaterEqual(rule.emit.policy.cooldown_frames, 30)

    def test_cooldown_suppresses_separated_repeated_lane_change_review_events(self):
        from trigger_engine.engine.event_policy import EventPolicyEngine

        rule = episode_rule("sdc_repeated_lane_change")
        rule = Rule(
            rule_id=rule.rule_id,
            kind=rule.kind,
            subject_type=rule.subject_type,
            condition=rule.condition,
            emit=RuleEmit(
                tag_name=rule.emit.tag_name,
                intent=rule.emit.intent,
                policy=EventPolicy(
                    cooldown_frames=30,
                    episode=ReviewEpisodePolicy(by="subject", mode="interval"),
                ),
            ),
        )
        events = tuple(
            TagEvent(
                scenario_id="scenario-review-optimization",
                source="unit",
                frame_index=i,
                timestamp_seconds=i * 0.1,
                tag_name="sdc_repeated_lane_change",
                subject_type="sdc_agent",
                subject_id=1,
                value=True,
                rule_id="sdc_repeated_lane_change",
                metadata={"intent": "review"},
            )
            for i in (5, 7, 10)
        )

        filtered = EventPolicyEngine().apply(events, (rule,))

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].frame_index, 5)


if __name__ == "__main__":
    unittest.main()
