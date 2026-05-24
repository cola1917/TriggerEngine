import unittest


class ClassicSdcOnlyRulePackContractTests(unittest.TestCase):
    def _rules(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        return RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML).rules

    def test_all_classic_rules_are_sdc_scoped(self):
        rules = self._rules()

        self.assertTrue(rules)
        self.assertTrue(
            all(rule.subject_type in {"sdc_agent", "sdc_pair"} for rule in rules),
            [(rule.rule_id, rule.subject_type) for rule in rules],
        )

    def test_stopped_rule_ids_and_tags_are_sdc_specific(self):
        rules = self._rules()
        by_id = {rule.rule_id: rule for rule in rules}

        forbidden_ids = {
            "vehicle_stopped",
            "vehicle_stopped_for_3_frames",
            "vehicle_stopped_at_red",
            "vehicle_still_stopped_at_red",
        }
        forbidden_tags = forbidden_ids

        self.assertFalse(forbidden_ids & set(by_id))
        self.assertFalse(forbidden_tags & {rule.emit.tag_name for rule in rules})

        self.assertIn("sdc_vehicle_stopped", by_id)
        self.assertEqual(by_id["sdc_vehicle_stopped"].subject_type, "sdc_agent")
        self.assertEqual(by_id["sdc_vehicle_stopped_for_3_frames"].condition.tag_name, "sdc_vehicle_stopped")
        self.assertEqual(by_id["sdc_vehicle_stopped_at_red"].subject_type, "sdc_agent")
        self.assertEqual(
            by_id["sdc_vehicle_still_stopped_at_red"].condition.tag_name,
            "sdc_vehicle_stopped_at_red",
        )

    def test_cut_in_review_rules_use_episode_policy(self):
        rules = self._rules()
        by_id = {rule.rule_id: rule for rule in rules}

        self.assertEqual(by_id["cut_in_candidate"].subject_type, "sdc_pair")
        self.assertEqual(by_id["cut_in_developing"].subject_type, "sdc_pair")
        self.assertEqual(by_id["cut_in_confirmed"].emit.policy.episode.mode, "interval")
        self.assertEqual(by_id["cut_in_risk"].emit.policy.episode.mode, "interval")

    def test_low_ttc_front_gate_is_not_zero_longitudinal(self):
        rules = self._rules()
        low_ttc = next(rule for rule in rules if rule.rule_id == "low_ttc_pair")
        pair_in_front = next(
            call for call in low_ttc.condition.calls
            if call.operator_name == "predicate.pair_in_front"
        )

        self.assertGreaterEqual(pair_in_front.args["min_longitudinal_m"], 1.0)


if __name__ == "__main__":
    unittest.main()
