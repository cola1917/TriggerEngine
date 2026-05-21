import unittest

from tests.test_rule_compiler_contract import registry_with_vehicle_ops
from tests.test_rule_dsl_temporal_contract import RULE_YAML


class RuleRegistryContractTests(unittest.TestCase):
    def test_registry_registers_yaml_and_activates_plan(self):
        from trigger_engine.engine.registry import RuleRegistry

        registry = RuleRegistry(operator_registry=registry_with_vehicle_ops())
        plan = registry.register_yaml("default", RULE_YAML)
        registry.activate("default")

        self.assertIs(registry.active_plan(), plan)
        self.assertEqual(registry.active_plan().plan_id, "default")

    def test_registry_rejects_active_plan_when_none_is_active(self):
        from trigger_engine.engine.registry import RuleRegistry, RuleRegistryError

        registry = RuleRegistry(operator_registry=registry_with_vehicle_ops())

        with self.assertRaisesRegex(RuleRegistryError, "active"):
            registry.active_plan()

    def test_registry_rejects_duplicate_plan_id(self):
        from trigger_engine.engine.registry import RuleRegistry, RuleRegistryError

        registry = RuleRegistry(operator_registry=registry_with_vehicle_ops())
        plan = registry.register_yaml("default", RULE_YAML)

        with self.assertRaisesRegex(RuleRegistryError, "default"):
            registry.register(plan)

    def test_registry_rejects_activation_of_unknown_plan(self):
        from trigger_engine.engine.registry import RuleRegistry, RuleRegistryError

        registry = RuleRegistry(operator_registry=registry_with_vehicle_ops())

        with self.assertRaisesRegex(RuleRegistryError, "missing"):
            registry.activate("missing")

    def test_registry_rejects_yaml_with_unregistered_operator(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.compiler import RuleCompileError
        from trigger_engine.operators.registry import OperatorRegistry

        registry = RuleRegistry(operator_registry=OperatorRegistry())

        with self.assertRaisesRegex(RuleCompileError, "predicate.type_is"):
            registry.register_yaml("default", RULE_YAML)


if __name__ == "__main__":
    unittest.main()
