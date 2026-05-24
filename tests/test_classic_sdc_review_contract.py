import unittest


class ClassicSdcReviewContractTests(unittest.TestCase):
    def test_classic_review_rules_are_sdc_centric(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rules = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules
        review_rules = [rule for rule in rules if rule.emit.intent == "review"]

        self.assertTrue(review_rules)
        self.assertTrue(
            all(rule.subject_type in {"sdc_agent", "sdc_pair"} for rule in review_rules),
            [(rule.rule_id, rule.subject_type) for rule in review_rules],
        )

        by_id = {rule.rule_id: rule for rule in rules}
        self.assertEqual(by_id["persistent_low_ttc_pair"].subject_type, "sdc_pair")
        self.assertEqual(by_id["cut_in_confirmed"].subject_type, "sdc_pair")
        self.assertEqual(by_id["red_light_running"].subject_type, "sdc_agent")


if __name__ == "__main__":
    unittest.main()
