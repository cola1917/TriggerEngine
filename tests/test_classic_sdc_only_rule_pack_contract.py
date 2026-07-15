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

    def test_classic_temporal_rules_use_seconds_not_frame_windows(self):
        from trigger_engine.rules.ast import SequenceTagCondition, SustainedTagCondition

        rules = self._rules()

        for rule in rules:
            if isinstance(rule.condition, SustainedTagCondition):
                self.assertIsNone(rule.condition.frames, rule.rule_id)
                self.assertIsNotNone(rule.condition.seconds, rule.rule_id)
            if isinstance(rule.condition, SequenceTagCondition):
                self.assertIsNone(rule.condition.within_frames, rule.rule_id)
                self.assertIsNotNone(rule.condition.within_seconds, rule.rule_id)

    def test_classic_rules_do_not_emit_frame_window_deprecation_diagnostics(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rule_set = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML)

        self.assertEqual(rule_set.diagnostics, ())

    def test_low_ttc_front_gate_is_not_zero_longitudinal(self):
        rules = self._rules()
        low_ttc = next(rule for rule in rules if rule.rule_id == "low_ttc_pair")
        pair_in_front = next(
            call for call in low_ttc.condition.calls
            if call.operator_name == "predicate.pair_in_front"
        )

        self.assertGreaterEqual(pair_in_front.args["min_longitudinal_m"], 1.0)

    def test_classic_motion_stability_operator_args_use_seconds(self):
        rules = self._rules()
        by_id = {rule.rule_id: rule for rule in rules}

        blocked_call = by_id["sdc_blocked_unable_to_proceed"].condition.calls[0]
        self.assertIn("min_stopped_duration_seconds", blocked_call.args)
        self.assertNotIn("min_stopped_frames", blocked_call.args)

        repeated_lane_change_call = next(
            call for call in by_id["sdc_repeated_lane_change"].condition.calls
            if call.operator_name == "predicate.sdc_repeated_lane_change"
        )
        self.assertIn("min_stable_duration_seconds", repeated_lane_change_call.args)
        self.assertNotIn("min_stable_frames", repeated_lane_change_call.args)


if __name__ == "__main__":
    unittest.main()
