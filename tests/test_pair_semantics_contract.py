import unittest

from tests.test_agent_pair_subject_contract import (
    AlwaysPairTrueOperator,
    agent,
    context_with_agents,
)


DIRECTED_PAIR_YAML = """
rules:
  - id: pair_rule
    subject: agent_pair
    when:
      all:
        - operator: predicate.agent_pair_always_true
    emit:
      tag: pair_rule
"""


UNORDERED_PAIR_YAML = """
rules:
  - id: pair_rule
    subject: agent_pair
    pair:
      mode: unordered
    when:
      all:
        - operator: predicate.agent_pair_always_true
    emit:
      tag: pair_rule
      intent: supporting
"""


class PairSemanticsContractTests(unittest.TestCase):
    def test_parser_defaults_agent_pair_rules_to_directed(self):
        from trigger_engine.rules.parser import RuleParser

        rule = RuleParser().parse_yaml(DIRECTED_PAIR_YAML).rules[0]

        self.assertEqual(rule.pair.mode, "directed")

    def test_parser_accepts_unordered_pair_mode(self):
        from trigger_engine.rules.parser import RuleParser

        rule = RuleParser().parse_yaml(UNORDERED_PAIR_YAML).rules[0]

        self.assertEqual(rule.pair.mode, "unordered")

    def test_parser_rejects_pair_mode_on_non_pair_subject(self):
        from trigger_engine.rules.parser import RuleParseError, RuleParser

        text = UNORDERED_PAIR_YAML.replace("subject: agent_pair", "subject: agent")

        with self.assertRaisesRegex(RuleParseError, "pair"):
            RuleParser().parse_yaml(text)

    def test_rule_engine_generates_canonical_unordered_pair_subjects(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysPairTrueOperator())
        rule_set = RuleParser().parse_yaml(UNORDERED_PAIR_YAML)

        events = RuleEngine(registry).evaluate(
            rule_set,
            context_with_agents(agent(3), agent(1), agent(2)),
        )

        self.assertEqual(
            [event.subject_id for event in events],
            ["1:3", "2:3", "1:2"],
        )
        self.assertEqual(
            [event.metadata["pair_mode"] for event in events],
            ["unordered", "unordered", "unordered"],
        )
        self.assertEqual(events[0].metadata["pair_member_ids"], (1, 3))

    def test_subject_cache_preserves_canonical_unordered_pair_subjects(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysPairTrueOperator())
        rule_set = RuleParser().parse_yaml(UNORDERED_PAIR_YAML)

        events = RuleEngine(registry).evaluate(
            rule_set,
            context_with_agents(agent(1), agent(2), agent(3)),
            subject_cache=SubjectCache(),
        )

        self.assertEqual(
            [event.subject_id for event in events],
            ["1:2", "1:3", "2:3"],
        )

    def test_rule_engine_keeps_directed_pair_subjects_backward_compatible(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysPairTrueOperator())
        rule_set = RuleParser().parse_yaml(DIRECTED_PAIR_YAML)

        events = RuleEngine(registry).evaluate(
            rule_set,
            context_with_agents(agent(1), agent(2)),
        )

        self.assertEqual([event.subject_id for event in events], ["1:2", "2:1"])
        self.assertEqual(events[0].metadata["pair_mode"], "directed")
        self.assertEqual(events[0].metadata["ego_id"], 1)
        self.assertEqual(events[0].metadata["target_id"], 2)


if __name__ == "__main__":
    unittest.main()
