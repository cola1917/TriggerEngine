from __future__ import annotations

from dataclasses import dataclass

from trigger_engine.operators.registry import OperatorRegistry, OperatorRegistryError
from trigger_engine.rules.ast import (
    AllCondition,
    Rule,
    RuleSet,
    SequenceTagCondition,
    SustainedTagCondition,
)


class RuleCompileError(Exception):
    pass


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    single_frame_rules: tuple[Rule, ...]
    temporal_rules: tuple[Rule, ...]
    operator_names: tuple[str, ...]


class RuleCompiler:
    def compile(
        self,
        plan_id: str,
        rule_set: RuleSet,
        operator_registry: OperatorRegistry,
    ) -> ExecutionPlan:
        single_frame_rules = []
        temporal_rules = []
        operator_names_set: set[str] = set()
        single_frame_emit_tags: dict[str, str] = {}  # tag_name -> subject_type

        for rule in rule_set.rules:
            if rule.kind == "single_frame":
                single_frame_rules.append(rule)
                if not isinstance(rule.condition, AllCondition):
                    raise RuleCompileError(
                        f"Single-frame rule '{rule.rule_id}' must use AllCondition"
                    )
                for call in rule.condition.calls:
                    try:
                        op = operator_registry.get(call.operator_name)
                    except OperatorRegistryError as exc:
                        raise RuleCompileError(str(exc)) from exc
                    if op.subject_type != rule.subject_type:
                        raise RuleCompileError(
                            f"Operator '{op.name}' subject_type='{op.subject_type}' "
                            f"does not match rule '{rule.rule_id}' subject_type='{rule.subject_type}'"
                        )
                    if op.result_kind != "predicate":
                        raise RuleCompileError(
                            f"Operator '{op.name}' result_kind='{op.result_kind}' "
                            f"is not 'predicate', required by rule '{rule.rule_id}'"
                        )
                    operator_names_set.add(call.operator_name)
                single_frame_emit_tags[rule.emit.tag_name] = rule.subject_type

            elif rule.kind == "temporal":
                temporal_rules.append(rule)
                if isinstance(rule.condition, SustainedTagCondition):
                    self._validate_sustained_rule(
                        rule, rule.condition, single_frame_emit_tags
                    )
                elif isinstance(rule.condition, SequenceTagCondition):
                    self._validate_sequence_rule(
                        rule, rule.condition, single_frame_emit_tags
                    )
                else:
                    raise RuleCompileError(
                        f"Temporal rule '{rule.rule_id}' must use a supported temporal condition"
                    )
            else:
                raise RuleCompileError(f"Unknown rule kind: '{rule.kind}'")

        return ExecutionPlan(
            plan_id=plan_id,
            single_frame_rules=tuple(single_frame_rules),
            temporal_rules=tuple(temporal_rules),
            operator_names=tuple(sorted(operator_names_set)),
        )

    def _validate_sustained_rule(
        self,
        rule: Rule,
        condition: SustainedTagCondition,
        single_frame_emit_tags: dict[str, str],
    ) -> None:
        source_tag = condition.tag_name
        if source_tag not in single_frame_emit_tags:
            raise RuleCompileError(
                f"Temporal rule '{rule.rule_id}' references unknown "
                f"source tag '{source_tag}'"
            )
        expected_subject = single_frame_emit_tags[source_tag]
        if rule.subject_type != expected_subject:
            raise RuleCompileError(
                f"Temporal rule '{rule.rule_id}' subject_type='{rule.subject_type}' "
                f"does not match source tag '{source_tag}' subject_type='{expected_subject}'"
            )
        if condition.frames is not None and condition.frames <= 0:
            raise RuleCompileError(
                f"Temporal rule '{rule.rule_id}' sustained.frames must be positive"
            )
        if condition.seconds is not None and condition.seconds <= 0:
            raise RuleCompileError(
                f"Temporal rule '{rule.rule_id}' sustained.seconds must be positive"
            )

    def _validate_sequence_rule(
        self,
        rule: Rule,
        condition: SequenceTagCondition,
        single_frame_emit_tags: dict[str, str],
    ) -> None:
        if len(condition.steps) < 2:
            raise RuleCompileError(
                f"Temporal rule '{rule.rule_id}' sequence must contain at least two steps"
            )
        if condition.within_frames is not None and condition.within_frames <= 0:
            raise RuleCompileError(
                f"Temporal rule '{rule.rule_id}' within_frames must be positive"
            )
        if condition.within_seconds is not None and condition.within_seconds <= 0:
            raise RuleCompileError(
                f"Temporal rule '{rule.rule_id}' within_seconds must be positive"
            )

        for step in condition.steps:
            source_tag = step.tag_name
            if source_tag not in single_frame_emit_tags:
                raise RuleCompileError(
                    f"Temporal rule '{rule.rule_id}' references unknown "
                    f"source tag '{source_tag}'"
                )
            expected_subject = single_frame_emit_tags[source_tag]
            if rule.subject_type != expected_subject:
                raise RuleCompileError(
                    f"Temporal rule '{rule.rule_id}' subject_type='{rule.subject_type}' "
                    f"does not match source tag '{source_tag}' subject_type='{expected_subject}'"
                )
