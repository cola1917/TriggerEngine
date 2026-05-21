import unittest


class ClassicScenarioPackContractTests(unittest.TestCase):
    def test_classic_yaml_parses_and_compiles(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import (
            CLASSIC_SCENARIO_RULES_YAML,
            register_classic_scenario_pack,
        )

        operator_registry = OperatorRegistry()
        rule_registry = RuleRegistry(operator_registry=operator_registry)
        plan = register_classic_scenario_pack(operator_registry, rule_registry, "classic_v1")

        self.assertIn("vehicle_stopped", CLASSIC_SCENARIO_RULES_YAML)
        self.assertEqual(plan.plan_id, "classic_v1")
        self.assertGreaterEqual(len(plan.single_frame_rules), 4)
        self.assertGreaterEqual(len(plan.temporal_rules), 4)
        self.assertIs(rule_registry.active_plan(), plan)


if __name__ == "__main__":
    unittest.main()
