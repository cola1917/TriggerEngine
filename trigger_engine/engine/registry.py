from __future__ import annotations

from trigger_engine.operators.registry import OperatorRegistry
from trigger_engine.rules.parser import RuleParser

from .compiler import ExecutionPlan, RuleCompiler


class RuleRegistryError(Exception):
    pass


class RuleRegistry:
    def __init__(self, operator_registry: OperatorRegistry) -> None:
        self._operator_registry = operator_registry
        self._plans: dict[str, ExecutionPlan] = {}
        self._active_plan_id: str | None = None

    def register(self, plan: ExecutionPlan) -> None:
        if plan.plan_id in self._plans:
            raise RuleRegistryError(f"Plan '{plan.plan_id}' is already registered")
        self._plans[plan.plan_id] = plan

    def register_yaml(self, name: str, yaml_text: str) -> ExecutionPlan:
        rule_set = RuleParser().parse_yaml(yaml_text)
        plan = RuleCompiler().compile(name, rule_set, self._operator_registry)
        self.register(plan)
        return plan

    def activate(self, plan_id: str) -> None:
        if plan_id not in self._plans:
            raise RuleRegistryError(f"Plan '{plan_id}' is not registered")
        self._active_plan_id = plan_id

    def active_plan(self) -> ExecutionPlan:
        if self._active_plan_id is None:
            raise RuleRegistryError("No active plan")
        return self._plans[self._active_plan_id]
