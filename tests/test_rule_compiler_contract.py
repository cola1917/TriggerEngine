import unittest
from dataclasses import is_dataclass

from tests.test_rule_dsl_temporal_contract import RULE_YAML


class TypeIsOperator:
    name = "predicate.type_is"
    result_kind = "predicate"
    subject_type = "agent"


class SpeedBelowOperator:
    name = "predicate.speed_below"
    result_kind = "predicate"
    subject_type = "agent"


class MetricSpeedOperator:
    name = "metric.speed"
    result_kind = "metric"
    subject_type = "agent"


def registry_with_vehicle_ops():
    from trigger_engine.operators.registry import OperatorRegistry

    registry = OperatorRegistry()
    registry.register(TypeIsOperator())
    registry.register(SpeedBelowOperator())
    return registry


class RuleCompilerContractTests(unittest.TestCase):
    def test_execution_plan_is_dataclass(self):
        from trigger_engine.engine.compiler import ExecutionPlan

        self.assertTrue(is_dataclass(ExecutionPlan))

    def test_compiler_builds_execution_plan_with_rule_partitions(self):
        from trigger_engine.engine.compiler import ExecutionPlan, RuleCompiler
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(RULE_YAML)
        plan = RuleCompiler().compile("default", rule_set, registry_with_vehicle_ops())

        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.plan_id, "default")
        self.assertEqual([rule.rule_id for rule in plan.single_frame_rules], ["vehicle_stopped"])
        self.assertEqual([rule.rule_id for rule in plan.temporal_rules], ["vehicle_stopped_for_3_frames"])
        self.assertEqual(plan.operator_names, ("predicate.speed_below", "predicate.type_is"))

    def test_compiler_rejects_missing_operator_at_config_time(self):
        from trigger_engine.engine.compiler import RuleCompileError, RuleCompiler
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(RULE_YAML)

        with self.assertRaisesRegex(RuleCompileError, "predicate.type_is"):
            RuleCompiler().compile("default", rule_set, OperatorRegistry())

    def test_compiler_rejects_subject_mismatch(self):
        from trigger_engine.engine.compiler import RuleCompileError, RuleCompiler
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.parser import RuleParser

        bad_operator = TypeIsOperator()
        bad_operator.subject_type = "frame"
        registry = OperatorRegistry()
        registry.register(bad_operator)
        registry.register(SpeedBelowOperator())
        rule_set = RuleParser().parse_yaml(RULE_YAML)

        with self.assertRaisesRegex(RuleCompileError, "subject"):
            RuleCompiler().compile("default", rule_set, registry)

    def test_compiler_rejects_metric_operator_in_single_frame_condition(self):
        from trigger_engine.engine.compiler import RuleCompileError, RuleCompiler
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(MetricSpeedOperator())
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: bad_metric
    kind: single_frame
    subject: agent
    when:
      all:
        - operator: metric.speed
    emit:
      tag: bad_metric
"""
        )

        with self.assertRaisesRegex(RuleCompileError, "predicate"):
            RuleCompiler().compile("default", rule_set, registry)

    def test_compiler_rejects_temporal_unknown_source_tag(self):
        from trigger_engine.engine.compiler import RuleCompileError, RuleCompiler
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: unknown_temporal
    kind: temporal
    subject: agent
    when:
      tag: unknown_single_frame_tag
      sustained:
        frames: 3
    emit:
      tag: unknown_temporal
"""
        )

        with self.assertRaisesRegex(RuleCompileError, "unknown_single_frame_tag"):
            RuleCompiler().compile("default", rule_set, registry_with_vehicle_ops())


if __name__ == "__main__":
    unittest.main()
