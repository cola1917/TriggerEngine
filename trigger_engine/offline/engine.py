from __future__ import annotations

from trigger_engine.engine.registry import RuleRegistry
from trigger_engine.engine.trigger_engine import TriggerEngine
from trigger_engine.operators.builtins import register_builtin_operators
from trigger_engine.operators.registry import OperatorRegistry
from trigger_engine.scenarios.classic import register_classic_scenario_pack


def build_default_engine(*, profile_rules: bool = False) -> TriggerEngine:
    operators = OperatorRegistry()
    register_builtin_operators(operators)
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    return TriggerEngine(operators, rules, profile_rules=profile_rules)
