from __future__ import annotations

import time
from dataclasses import dataclass, field

from trigger_engine.alignment.context import AlignmentContext
from trigger_engine.data.frames import ScenarioBundle
from trigger_engine.operators.registry import OperatorRegistry
from trigger_engine.rules.ast import RuleSet, SequenceTagCondition, SustainedTagCondition
from trigger_engine.rules.engine import RuleEngine
from trigger_engine.rules.events import TagEvent

from .event_policy import EventPolicyEngine
from .registry import RuleRegistry
from .subjects import SubjectCache
from .timeline import TagKey, TagTimeline


@dataclass(frozen=True)
class EngineStats:
    input_frames: int
    future_frames: int
    single_frame_rules: int
    temporal_rules: int
    events_emitted: int


@dataclass(frozen=True)
class EngineDiagnostic:
    level: str
    message: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineResult:
    scenario_id: str
    source: str | None
    plan_id: str
    events: tuple[TagEvent, ...]
    stats: EngineStats
    diagnostics: tuple[EngineDiagnostic, ...]


@dataclass(frozen=True)
class GatedRule:
    rule: object
    predecessor_tags: tuple[str, ...]


class TemporalRuleEngine:
    def evaluate(
        self,
        rules: tuple,
        context: AlignmentContext,
        timeline: TagTimeline,
        subject_cache=None,
        profile: dict[str, dict[str, object]] | None = None,
    ) -> tuple[TagEvent, ...]:
        events: list[TagEvent] = []

        for rule in rules:
            started = time.perf_counter() if profile is not None else None
            before = len(events)
            if isinstance(rule.condition, SustainedTagCondition):
                events.extend(self._evaluate_sustained(rule, context, timeline, subject_cache))
            elif isinstance(rule.condition, SequenceTagCondition):
                events.extend(self._evaluate_sequence(rule, context, timeline, subject_cache))
            if profile is not None:
                elapsed = time.perf_counter() - started
                item = profile.setdefault(
                    rule.rule_id,
                    {
                        "rule_id": rule.rule_id,
                        "tag_name": rule.emit.tag_name,
                        "rule_kind": "temporal",
                        "subject_type": rule.subject_type,
                        "seconds": 0.0,
                        "events_emitted": 0,
                        "calls": 0,
                    },
                )
                item["seconds"] += elapsed
                item["events_emitted"] += len(events) - before
                item["calls"] += 1

        return tuple(events)

    def _evaluate_sustained(
        self,
        rule,
        context: AlignmentContext,
        timeline: TagTimeline,
        subject_cache=None,
    ) -> list[TagEvent]:
        events: list[TagEvent] = []

        for subject_id in timeline.subject_ids_for(
            rule.condition.tag_name, rule.subject_type
        ):
            key = TagKey(
                tag_name=rule.condition.tag_name,
                subject_type=rule.subject_type,
                subject_id=subject_id,
            )
            for step_index in timeline.frames_for(key):
                aligned_frame = self._aligned_frame_by_step(context, step_index)
                if aligned_frame is None:
                    continue
                key = TagKey(
                    tag_name=rule.condition.tag_name,
                    subject_type=rule.subject_type,
                    subject_id=subject_id,
                )

                if rule.condition.seconds is not None:
                    ok, supporting = timeline.sustained_seconds(
                        key, step_index, rule.condition.seconds
                    )
                else:
                    ok, supporting = timeline.sustained(
                        key, step_index, rule.condition.frames
                    )

                if ok:
                    metadata: dict[str, object] = {
                        "rule_kind": "temporal",
                        "temporal_kind": "sustained",
                        "source_tag": rule.condition.tag_name,
                        "supporting_frame_indices": supporting,
                        "supporting_timestamps_seconds": tuple(
                            timeline.timestamp_at(i) for i in supporting
                        ),
                        "first_matched_frame_index": supporting[0],
                        "last_matched_frame_index": supporting[-1],
                        "first_matched_timestamp_seconds": timeline.timestamp_at(supporting[0]),
                        "last_matched_timestamp_seconds": timeline.timestamp_at(supporting[-1]),
                    }
                    if rule.condition.frames is not None:
                        metadata["sustained_frames"] = rule.condition.frames
                    if rule.condition.seconds is not None:
                        metadata["sustained_seconds"] = rule.condition.seconds
                    metadata["supporting_event_metadata"] = self._supporting_event_metadata(
                        timeline, (key,), supporting,
                    )
                    events.append(
                        self._build_temporal_event(
                            rule, context, aligned_frame, subject_id, metadata,
                        )
                    )

        return events

    def _evaluate_sequence(
        self,
        rule,
        context: AlignmentContext,
        timeline: TagTimeline,
        subject_cache=None,
    ) -> list[TagEvent]:
        events: list[TagEvent] = []
        source_tags = tuple(step.tag_name for step in rule.condition.steps)
        if not source_tags:
            return events

        candidate_subject_ids = None
        for tag_name in source_tags:
            ids = set(timeline.subject_ids_for(tag_name, rule.subject_type))
            candidate_subject_ids = ids if candidate_subject_ids is None else candidate_subject_ids & ids
        if not candidate_subject_ids:
            return events

        last_tag = source_tags[-1]
        for subject_id in sorted(candidate_subject_ids, key=str):
            last_key = TagKey(last_tag, rule.subject_type, subject_id)
            for step_index in timeline.frames_for(last_key):
                aligned_frame = self._aligned_frame_by_step(context, step_index)
                if aligned_frame is None:
                    continue
                keys = tuple(
                    TagKey(
                        tag_name=tag_name,
                        subject_type=rule.subject_type,
                        subject_id=subject_id,
                    )
                    for tag_name in source_tags
                )

                if rule.condition.within_seconds is not None:
                    ok, supporting = timeline.sequence_seconds(
                        keys,
                        step_index,
                        rule.condition.within_seconds,
                        rule.condition.max_gap_frames,
                    )
                else:
                    ok, supporting = timeline.sequence(
                        keys, step_index, rule.condition.within_frames
                    )

                if ok:
                    metadata: dict[str, object] = {
                        "rule_kind": "temporal",
                        "temporal_kind": "sequence",
                        "source_tags": source_tags,
                        "supporting_frame_indices": supporting,
                        "supporting_timestamps_seconds": tuple(
                            timeline.timestamp_at(i) for i in supporting
                        ),
                        "first_matched_frame_index": supporting[0],
                        "last_matched_frame_index": supporting[-1],
                        "first_matched_timestamp_seconds": timeline.timestamp_at(supporting[0]),
                        "last_matched_timestamp_seconds": timeline.timestamp_at(supporting[-1]),
                    }
                    if rule.condition.within_frames is not None:
                        metadata["within_frames"] = rule.condition.within_frames
                    if rule.condition.within_seconds is not None:
                        metadata["within_seconds"] = rule.condition.within_seconds
                    if rule.condition.max_gap_frames is not None:
                        metadata["max_gap_frames"] = rule.condition.max_gap_frames
                    metadata["supporting_event_metadata"] = self._supporting_event_metadata(
                        timeline, keys, supporting,
                    )
                    events.append(
                        self._build_temporal_event(
                            rule, context, aligned_frame, subject_id, metadata,
                        )
                    )

        return events

    def _build_temporal_event(
        self,
        rule,
        context: AlignmentContext,
        aligned_frame,
        subject_id: str | int | None,
        metadata: dict[str, object],
    ) -> TagEvent:
        merged = dict(rule.emit.metadata)
        merged.update(metadata)
        merged["intent"] = rule.emit.intent
        if rule.subject_type == "sdc_agent":
            merged.setdefault("ego_id", context.sdc_track_id)
            merged.setdefault("ego_role", "sdc")
        elif rule.subject_type == "sdc_pair":
            merged.setdefault("pair_mode", "sdc")
            merged.setdefault("ego_id", context.sdc_track_id)
            merged.setdefault("ego_role", "sdc")
            if isinstance(subject_id, str) and ":" in subject_id:
                parts = subject_id.split(":", 1)
                merged.setdefault("target_id", int(parts[1]))
            merged.setdefault("target_role", "interactive_agent")
        return TagEvent(
            scenario_id=context.scenario_id,
            source=context.source,
            frame_index=aligned_frame.frame.step_index,
            timestamp_seconds=aligned_frame.frame.timestamp_seconds,
            tag_name=rule.emit.tag_name,
            subject_type=rule.subject_type,
            subject_id=subject_id,
            value=rule.emit.value,
            rule_id=rule.rule_id,
            metadata=merged,
        )

    def _supporting_event_metadata(
        self,
        timeline: TagTimeline,
        keys: tuple[TagKey, ...],
        supporting: tuple[int, ...],
    ) -> tuple[dict[str, object], ...]:
        details = []
        for index, frame_index in enumerate(supporting):
            key = keys[index] if len(keys) > 1 else keys[0]
            event = timeline.event_at(key, frame_index)
            if event is None:
                continue
            details.append({
                "tag_name": event.tag_name,
                "frame_index": event.frame_index,
                "timestamp_seconds": event.timestamp_seconds,
                "metadata": event.metadata,
            })
        return tuple(details)

    def _aligned_frame_by_step(
        self,
        context: AlignmentContext,
        step_index: int,
    ):
        for aligned_frame in context.input_frames:
            if aligned_frame.frame.step_index == step_index:
                return aligned_frame
        return None

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
        elif subject_type in ("agent_pair", "sdc_pair"):
            from trigger_engine.operators.builtins import AgentPairSubject

            agents = [a for a in aligned_frame.frame.agent_states if a.valid]
            pairs = []
            for i, ego in enumerate(agents):
                for j, other in enumerate(agents):
                    if i != j:
                        pairs.append(AgentPairSubject(ego=ego, other=other))
            return pairs
        elif subject_type == "sdc_agent":
            return list(aligned_frame.frame.agent_states)
        return []

    def _get_subject_id(self, subject_type: str, subject) -> str | int | None:
        if subject_type in ("agent", "sdc_agent"):
            return subject.track_id
        elif subject_type == "lane":
            return subject.lane_id
        elif subject_type in ("agent_pair", "sdc_pair"):
            return subject.subject_id
        return None


class TriggerEngine:
    def __init__(
        self,
        operator_registry: OperatorRegistry,
        rule_registry: RuleRegistry,
        rule_engine: RuleEngine | None = None,
        subject_cache=None,
        profile_rules: bool = False,
    ) -> None:
        self._operator_registry = operator_registry
        self._rule_registry = rule_registry
        self._rule_engine = rule_engine or RuleEngine(operator_registry)
        self._temporal_engine = TemporalRuleEngine()
        self._policy_engine = EventPolicyEngine()
        self._subject_cache = subject_cache
        self._profile_rules = profile_rules

    def evaluate(self, context: AlignmentContext) -> EngineResult:
        plan = self._rule_registry.active_plan()
        subject_cache = self._subject_cache or SubjectCache()
        diagnostics: list[EngineDiagnostic] = [
            EngineDiagnostic(
                item.level,
                "rule_deprecation",
                {
                    "code": item.code,
                    "message": item.message,
                    "rule_id": item.rule_id,
                    "field_path": item.field_path,
                },
            )
            for item in getattr(plan, "diagnostics", ())
        ]
        rule_profile = {} if self._profile_rules else None

        gated_rules = self._gated_rules(plan)
        gated_rule_ids = {item.rule.rule_id for item in gated_rules}
        ungated_rules = tuple(
            rule
            for rule in plan.single_frame_rules
            if rule.rule_id not in gated_rule_ids
        )

        # Single-frame rules
        single_events = list(self._rule_engine.evaluate(
            RuleSet(rules=ungated_rules), context, subject_cache=subject_cache,
            profile=rule_profile,
        ))
        timeline = TagTimeline.from_events(single_events)

        completed_tags = {rule.emit.tag_name for rule in ungated_rules}
        pending = list(gated_rules)
        while pending:
            progressed = False
            remaining = []
            for gated in pending:
                if not all(tag in completed_tags for tag in gated.predecessor_tags):
                    remaining.append(gated)
                    continue

                allowed_subject_ids = set()
                for tag_name in gated.predecessor_tags:
                    allowed_subject_ids.update(
                        timeline.subject_ids_for(tag_name, gated.rule.subject_type)
                    )

                if allowed_subject_ids:
                    gated_events = self._rule_engine.evaluate(
                        RuleSet(rules=(gated.rule,)),
                        context,
                        subject_cache=subject_cache,
                        subject_id_filters={gated.rule.rule_id: allowed_subject_ids},
                        profile=rule_profile,
                    )
                    single_events.extend(gated_events)
                    timeline = TagTimeline.from_events(single_events)
                    emitted = len(gated_events)
                else:
                    emitted = 0

                completed_tags.add(gated.rule.emit.tag_name)
                diagnostics.append(
                    EngineDiagnostic(
                        "info",
                        "sequence_candidate_gating",
                        {
                            "rule_id": gated.rule.rule_id,
                            "tag_name": gated.rule.emit.tag_name,
                            "predecessor_tags": gated.predecessor_tags,
                            "candidate_subjects": len(allowed_subject_ids),
                            "events_emitted": emitted,
                        },
                    )
                )
                progressed = True

            if not progressed:
                # Defensive fallback: preserve correctness if an unexpected dependency cycle appears.
                fallback_rules = tuple(item.rule for item in remaining)
                fallback_events = self._rule_engine.evaluate(
                    RuleSet(rules=fallback_rules),
                    context,
                    subject_cache=subject_cache,
                    profile=rule_profile,
                )
                single_events.extend(fallback_events)
                timeline = TagTimeline.from_events(single_events)
                diagnostics.append(
                    EngineDiagnostic(
                        "warning",
                        "sequence_candidate_gating_fallback",
                        {"rule_ids": tuple(rule.rule_id for rule in fallback_rules)},
                    )
                )
                break
            pending = remaining

        # Build timeline from raw single-frame events (before policy filtering)
        single_events_tuple = tuple(single_events)

        # Temporal rules
        temporal_events = self._temporal_engine.evaluate(
            plan.temporal_rules, context, timeline,
            subject_cache=subject_cache,
            profile=rule_profile,
        )

        # Apply event policy after temporal detection
        all_rules = plan.single_frame_rules + plan.temporal_rules
        all_events = self._policy_engine.apply(
            single_events_tuple + temporal_events, all_rules
        )
        all_events = self._with_evaluation_mode(all_events, context)

        stats = EngineStats(
            input_frames=len(context.input_frames),
            future_frames=len(context.future_frames),
            single_frame_rules=len(plan.single_frame_rules),
            temporal_rules=len(plan.temporal_rules),
            events_emitted=len(all_events),
        )
        if rule_profile is not None:
            profile_order = {
                rule.rule_id: index
                for index, rule in enumerate(plan.single_frame_rules + plan.temporal_rules)
            }
            diagnostics.extend(
                EngineDiagnostic("info", "rule_profile", profile)
                for profile in sorted(
                    rule_profile.values(),
                    key=lambda item: (
                        profile_order.get(str(item.get("rule_id", "")), len(profile_order)),
                        str(item.get("rule_id", "")),
                    ),
                )
            )

        return EngineResult(
            scenario_id=context.scenario_id,
            source=context.source,
            plan_id=plan.plan_id,
            events=all_events,
            stats=stats,
            diagnostics=tuple(diagnostics),
        )

    def evaluate_offline_scene(self, bundle: ScenarioBundle) -> EngineResult:
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        context = ScenarioAlignment().align_full_scene(bundle)
        return self.evaluate(context)

    def _with_evaluation_mode(
        self,
        events: tuple[TagEvent, ...],
        context: AlignmentContext,
    ) -> tuple[TagEvent, ...]:
        from dataclasses import replace

        mode = getattr(context, "evaluation_mode", "causal_watermark")
        if mode == "causal_watermark":
            return events
        updated = []
        for event in events:
            metadata = dict(event.metadata)
            metadata["evaluation_mode"] = mode
            updated.append(replace(event, metadata=metadata))
        return tuple(updated)

    def _gated_rules(self, plan) -> tuple[GatedRule, ...]:
        rule_by_tag = {
            rule.emit.tag_name: rule
            for rule in plan.single_frame_rules
        }
        sustained_source_tags = {
            rule.condition.tag_name
            for rule in plan.temporal_rules
            if isinstance(rule.condition, SustainedTagCondition)
        }
        sequence_first_tags = set()
        predecessor_tags_by_tag: dict[str, set[str]] = {}

        for rule in plan.temporal_rules:
            if not isinstance(rule.condition, SequenceTagCondition):
                continue
            if rule.subject_type not in ("agent_pair", "sdc_pair"):
                continue
            steps = tuple(step.tag_name for step in rule.condition.steps)
            if not steps:
                continue
            sequence_first_tags.add(steps[0])
            for index in range(1, len(steps)):
                predecessor_tags_by_tag.setdefault(steps[index], set()).add(steps[index - 1])

        gated = []
        for tag_name, predecessor_tags in predecessor_tags_by_tag.items():
            source_rule = rule_by_tag.get(tag_name)
            if source_rule is None:
                continue
            if tag_name in sustained_source_tags or tag_name in sequence_first_tags:
                continue
            gated.append(
                GatedRule(
                    rule=source_rule,
                    predecessor_tags=tuple(sorted(predecessor_tags)),
                )
            )
        return tuple(gated)
