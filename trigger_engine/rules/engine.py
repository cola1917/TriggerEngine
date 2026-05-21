from __future__ import annotations

from trigger_engine.alignment.context import AlignmentContext
from trigger_engine.operators.registry import OperatorRegistry

from .ast import RuleSet
from .events import TagEvent


class RuleEngineError(Exception):
    pass


class RuleEngine:
    def __init__(self, registry: OperatorRegistry) -> None:
        self._registry = registry

    def evaluate(
        self,
        rule_set: RuleSet,
        context: AlignmentContext,
        subject_cache=None,
        subject_id_filters: dict[str, set[str | int | None]] | None = None,
    ) -> tuple[TagEvent, ...]:
        events: list[TagEvent] = []

        for rule in rule_set.rules:
            allowed_subject_ids = (
                subject_id_filters.get(rule.rule_id)
                if subject_id_filters is not None
                else None
            )
            for aligned_frame in context.input_frames:
                if subject_cache is not None:
                    subjects = subject_cache.subjects_for_rule(
                        rule,
                        aligned_frame,
                        allowed_subject_ids=allowed_subject_ids,
                    )
                else:
                    subjects = self._get_subjects(rule.subject_type, aligned_frame)
                for subject in subjects:
                    subject_id = self._get_subject_id(rule.subject_type, subject)
                    if (
                        allowed_subject_ids is not None
                        and subject_id not in allowed_subject_ids
                    ):
                        continue
                    operator_results = {}
                    all_true = True

                    for call in rule.condition.calls:
                        operator = self._registry.get(call.operator_name)
                        if operator.subject_type != rule.subject_type:
                            raise RuleEngineError(
                                f"Operator '{operator.name}' subject_type='{operator.subject_type}' "
                                f"does not match rule subject_type='{rule.subject_type}'"
                            )
                        result = operator.evaluate(
                            context=context,
                            frame=aligned_frame,
                            subject=subject,
                            args=call.args,
                        )
                        if operator.result_kind == "predicate" and not isinstance(result.value, bool):
                            raise RuleEngineError(
                                f"Predicate operator '{operator.name}' must return bool, "
                                f"got {type(result.value).__name__}"
                            )
                        operator_results[call.operator_name] = result.value
                        if not result.value:
                            all_true = False
                            break

                    if all_true:
                        event = TagEvent(
                            scenario_id=context.scenario_id,
                            source=context.source,
                            frame_index=aligned_frame.frame.step_index,
                            timestamp_seconds=aligned_frame.frame.timestamp_seconds,
                            tag_name=rule.emit.tag_name,
                            subject_type=rule.subject_type,
                            subject_id=subject_id,
                            value=rule.emit.value,
                            rule_id=rule.rule_id,
                            metadata={
                                "rule_kind": "single_frame",
                                "operator_results": operator_results,
                            },
                        )
                        events.append(event)

        return tuple(events)

    def _get_subjects(self, subject_type: str, aligned_frame) -> list:
        if subject_type == "agent":
            return list(aligned_frame.frame.agent_states)
        elif subject_type == "frame":
            return [aligned_frame]
        elif subject_type == "lane":
            return [
                type("LaneSubject", (), {"lane_id": tl.lane_id})()
                for tl in aligned_frame.frame.traffic_lights
            ]
        elif subject_type == "scenario":
            return [aligned_frame]
        elif subject_type == "agent_pair":
            from trigger_engine.operators.builtins import AgentPairSubject

            agents = [a for a in aligned_frame.frame.agent_states if a.valid]
            pairs = []
            for i, ego in enumerate(agents):
                for j, other in enumerate(agents):
                    if i != j:
                        pairs.append(AgentPairSubject(ego=ego, other=other))
            return pairs
        return []

    def _get_subject_id(self, subject_type: str, subject) -> str | int | None:
        if subject_type == "agent":
            return subject.track_id
        elif subject_type == "lane":
            return subject.lane_id
        elif subject_type == "agent_pair":
            return subject.subject_id
        return None
