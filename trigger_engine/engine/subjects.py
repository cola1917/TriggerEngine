from __future__ import annotations

import math
from dataclasses import dataclass

from trigger_engine.rules.ast import AllCondition, Rule


@dataclass(frozen=True)
class PairCandidatePredicate:
    operator_name: str
    args: dict[str, object]

    @property
    def search_radius_m(self) -> float | None:
        if self.operator_name in {
            "predicate.close_lateral_gap",
            "predicate.lateral_gap_between",
            "predicate.same_path_overlap",
        }:
            max_lat = float(self.args["max_lateral_m"])
            max_long = float(self.args["max_longitudinal_m"])
            return math.sqrt(max_lat * max_lat + max_long * max_long)
        return None

    def matches(self, ego, other) -> bool:
        dx = other.center.x - ego.center.x
        dy = other.center.y - ego.center.y
        lon, lat = _rotate(dx, dy, ego.heading)
        lat_abs = abs(lat)

        if self.operator_name == "predicate.close_lateral_gap":
            return (
                lat_abs <= float(self.args["max_lateral_m"])
                and abs(lon) <= float(self.args["max_longitudinal_m"])
            )
        if self.operator_name == "predicate.lateral_gap_between":
            return (
                lat_abs <= float(self.args["max_lateral_m"])
                and abs(lon) <= float(self.args["max_longitudinal_m"])
            )
        if self.operator_name == "predicate.same_path_overlap":
            return (
                lat_abs <= float(self.args["max_lateral_m"])
                and float(self.args.get("min_longitudinal_m", 0.0))
                <= lon
                <= float(self.args["max_longitudinal_m"])
            )
        if self.operator_name == "predicate.pair_in_front":
            return (
                lat_abs <= float(self.args.get("max_lateral_m", 4.0))
                and lon >= float(self.args.get("min_longitudinal_m", 0.0))
            )
        if self.operator_name == "predicate.low_ttc":
            return (
                lat_abs <= float(self.args.get("max_lateral_m", 4.0))
                and lon > 0.0
            )
        return True


@dataclass(frozen=True)
class PairCandidatePlan:
    rule_id: str
    predicates: tuple[PairCandidatePredicate, ...]

    @property
    def can_prune(self) -> bool:
        return bool(self.predicates)

    @property
    def search_radius_m(self) -> float | None:
        radii = [
            predicate.search_radius_m
            for predicate in self.predicates
            if predicate.search_radius_m is not None
        ]
        if not radii:
            return None
        return min(radii)

    def matches(self, ego, other) -> bool:
        return all(predicate.matches(ego, other) for predicate in self.predicates)


class PairGeometryCache:
    MIN_VECTOR_AGENT_COUNT = 32

    def __init__(self, agents: list) -> None:
        import numpy as np

        self._np = np
        self._agents = agents
        self._xs = np.array([agent.center.x for agent in agents], dtype=float)
        self._ys = np.array([agent.center.y for agent in agents], dtype=float)
        headings = np.array([agent.heading for agent in agents], dtype=float)
        self._cos = np.cos(headings)
        self._sin = np.sin(headings)
        self._lon = None
        self._lat = None

    @classmethod
    def should_vectorize(cls, agent_count: int, plan: PairCandidatePlan) -> bool:
        return agent_count >= cls.MIN_VECTOR_AGENT_COUNT and plan.can_prune

    def candidate_index_pairs(self, plan: PairCandidatePlan) -> list[tuple[int, int]]:
        np = self._np
        count = len(self._agents)
        if count == 0:
            return []

        lon, lat = self._relative_lon_lat()
        lat_abs = np.abs(lat)
        mask = ~np.eye(count, dtype=bool)

        for predicate in plan.predicates:
            args = predicate.args
            if predicate.operator_name == "predicate.close_lateral_gap":
                mask &= lat_abs <= float(args["max_lateral_m"])
                mask &= np.abs(lon) <= float(args["max_longitudinal_m"])
            elif predicate.operator_name == "predicate.lateral_gap_between":
                mask &= lat_abs <= float(args["max_lateral_m"])
                mask &= np.abs(lon) <= float(args["max_longitudinal_m"])
            elif predicate.operator_name == "predicate.same_path_overlap":
                mask &= lat_abs <= float(args["max_lateral_m"])
                mask &= lon >= float(args.get("min_longitudinal_m", 0.0))
                mask &= lon <= float(args["max_longitudinal_m"])
            elif predicate.operator_name == "predicate.pair_in_front":
                mask &= lat_abs <= float(args.get("max_lateral_m", 4.0))
                mask &= lon >= float(args.get("min_longitudinal_m", 0.0))
            elif predicate.operator_name == "predicate.low_ttc":
                mask &= lat_abs <= float(args.get("max_lateral_m", 4.0))
                mask &= lon > 0.0

        ego_indices, other_indices = np.nonzero(mask)
        return [
            (int(ego_index), int(other_index))
            for ego_index, other_index in zip(ego_indices, other_indices)
        ]

    def _relative_lon_lat(self):
        if self._lon is not None and self._lat is not None:
            return self._lon, self._lat

        dx = self._xs[None, :] - self._xs[:, None]
        dy = self._ys[None, :] - self._ys[:, None]
        self._lon = dx * self._cos[:, None] + dy * self._sin[:, None]
        self._lat = -dx * self._sin[:, None] + dy * self._cos[:, None]
        return self._lon, self._lat


class SubjectCache:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, str], list] = {}
        self._rule_cache: dict[tuple[str, str, int, str], list] = {}
        self._build_counts: dict[tuple[str, int, str], int] = {}
        self._rule_build_counts: dict[tuple[str, str, int, str], int] = {}
        self._rule_candidate_counts: dict[tuple[str, str, int, str], int] = {}
        self._rule_pair_scan_counts: dict[tuple[str, str, int, str], int] = {}
        self._rule_geometry_modes: dict[tuple[str, str, int, str], str] = {}

    def subjects_for(self, subject_type: str, aligned_frame) -> list:
        key = self._key(aligned_frame, subject_type)
        if key in self._cache:
            return self._cache[key]

        subjects = self._build_subjects(subject_type, aligned_frame)
        self._cache[key] = subjects
        self._build_counts[key] = self._build_counts.get(key, 0) + 1
        return subjects

    def subjects_for_rule(
        self,
        rule: Rule,
        aligned_frame,
        allowed_subject_ids: set[str | int | None] | None = None,
    ) -> list:
        if allowed_subject_ids is not None:
            return self._build_filtered_subjects(rule, aligned_frame, allowed_subject_ids)

        if rule.subject_type != "agent_pair":
            return self.subjects_for(rule.subject_type, aligned_frame)

        plan = build_pair_candidate_plan(rule)
        if not plan.can_prune:
            return self.subjects_for(rule.subject_type, aligned_frame)

        key = self._rule_key(aligned_frame, rule.rule_id, rule.subject_type)
        if key in self._rule_cache:
            return self._rule_cache[key]

        subjects = self._build_agent_pair_candidates(aligned_frame, plan)
        scan_count = self._last_pair_scan_count
        self._rule_cache[key] = subjects
        self._rule_build_counts[key] = self._rule_build_counts.get(key, 0) + 1
        self._rule_candidate_counts[key] = len(subjects)
        self._rule_pair_scan_counts[key] = scan_count
        self._rule_geometry_modes[key] = self._last_geometry_mode
        return subjects

    def build_count(self, subject_type: str, step_index: int) -> int:
        return sum(
            count
            for (_, cached_step, cached_subject_type), count in self._build_counts.items()
            if cached_step == step_index and cached_subject_type == subject_type
        )

    def rule_build_count(self, rule_id: str, subject_type: str, step_index: int) -> int:
        return sum(
            count
            for (_, cached_rule_id, cached_step, cached_subject_type), count
            in self._rule_build_counts.items()
            if (
                cached_rule_id == rule_id
                and cached_step == step_index
                and cached_subject_type == subject_type
            )
        )

    def rule_candidate_count(self, rule_id: str, subject_type: str, step_index: int) -> int:
        return sum(
            count
            for (_, cached_rule_id, cached_step, cached_subject_type), count
            in self._rule_candidate_counts.items()
            if (
                cached_rule_id == rule_id
                and cached_step == step_index
                and cached_subject_type == subject_type
            )
        )

    def rule_pair_scan_count(self, rule_id: str, subject_type: str, step_index: int) -> int:
        return sum(
            count
            for (_, cached_rule_id, cached_step, cached_subject_type), count
            in self._rule_pair_scan_counts.items()
            if (
                cached_rule_id == rule_id
                and cached_step == step_index
                and cached_subject_type == subject_type
            )
        )

    def rule_geometry_mode(self, rule_id: str, subject_type: str, step_index: int) -> str | None:
        for (_, cached_rule_id, cached_step, cached_subject_type), mode in self._rule_geometry_modes.items():
            if (
                cached_rule_id == rule_id
                and cached_step == step_index
                and cached_subject_type == subject_type
            ):
                return mode
        return None

    @staticmethod
    def _build_subjects(subject_type: str, aligned_frame) -> list:
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

    _last_pair_scan_count = 0
    _last_geometry_mode = "scalar"

    def _build_agent_pair_candidates(self, aligned_frame, plan: PairCandidatePlan) -> list:
        from trigger_engine.operators.builtins import AgentPairSubject

        agents = [a for a in aligned_frame.frame.agent_states if a.valid]
        if PairGeometryCache.should_vectorize(len(agents), plan):
            geometry = PairGeometryCache(agents)
            index_pairs = geometry.candidate_index_pairs(plan)
            self._last_pair_scan_count = len(index_pairs)
            self._last_geometry_mode = "numpy"
            return [
                AgentPairSubject(ego=agents[i], other=agents[j])
                for i, j in index_pairs
            ]

        radius = plan.search_radius_m
        radius_sq = radius * radius if radius is not None else None

        pairs = []
        pair_scan_count = 0
        for i, ego in enumerate(agents):
            for j, other in enumerate(agents):
                if i == j:
                    continue
                if radius_sq is not None:
                    dx = other.center.x - ego.center.x
                    dy = other.center.y - ego.center.y
                    if dx * dx + dy * dy > radius_sq:
                        continue
                pair_scan_count += 1
                if plan.matches(ego, other):
                    pairs.append(AgentPairSubject(ego=ego, other=other))
        self._last_pair_scan_count = pair_scan_count
        self._last_geometry_mode = "scalar"
        return pairs

    def _build_filtered_subjects(
        self,
        rule: Rule,
        aligned_frame,
        allowed_subject_ids: set[str | int | None],
    ) -> list:
        if rule.subject_type == "agent_pair":
            return self._build_filtered_agent_pair_subjects(rule, aligned_frame, allowed_subject_ids)

        subjects = self._build_subjects(rule.subject_type, aligned_frame)
        return [
            subject
            for subject in subjects
            if self._subject_id(rule.subject_type, subject) in allowed_subject_ids
        ]

    def _build_filtered_agent_pair_subjects(
        self,
        rule: Rule,
        aligned_frame,
        allowed_subject_ids: set[str | int | None],
    ) -> list:
        from trigger_engine.operators.builtins import AgentPairSubject

        plan = build_pair_candidate_plan(rule)
        agents = [a for a in aligned_frame.frame.agent_states if a.valid]
        agents_by_id = {str(agent.track_id): agent for agent in agents}
        order = {str(agent.track_id): index for index, agent in enumerate(agents)}
        pairs = []

        for subject_id in sorted(
            allowed_subject_ids,
            key=lambda item: _pair_order_key(item, order),
        ):
            if not isinstance(subject_id, str) or ":" not in subject_id:
                continue
            ego_id, other_id = subject_id.split(":", 1)
            ego = agents_by_id.get(ego_id)
            other = agents_by_id.get(other_id)
            if ego is None or other is None:
                continue
            if ego_id == other_id:
                continue
            if plan.can_prune and not plan.matches(ego, other):
                continue
            pairs.append(AgentPairSubject(ego=ego, other=other))
        return pairs

    @staticmethod
    def _subject_id(subject_type: str, subject):
        if subject_type == "agent":
            return subject.track_id
        if subject_type == "lane":
            return subject.lane_id
        if subject_type == "agent_pair":
            return subject.subject_id
        return None

    @staticmethod
    def _key(aligned_frame, subject_type: str) -> tuple[str, int, str]:
        return (
            aligned_frame.frame.scenario_id,
            aligned_frame.frame.step_index,
            subject_type,
        )

    @staticmethod
    def _rule_key(aligned_frame, rule_id: str, subject_type: str) -> tuple[str, str, int, str]:
        return (
            aligned_frame.frame.scenario_id,
            rule_id,
            aligned_frame.frame.step_index,
            subject_type,
        )


def build_pair_candidate_plan(rule: Rule) -> PairCandidatePlan:
    if rule.subject_type != "agent_pair" or not isinstance(rule.condition, AllCondition):
        return PairCandidatePlan(rule.rule_id, ())

    predicates = []
    for call in rule.condition.calls:
        predicate = _candidate_predicate_for(call.operator_name, call.args)
        if predicate is not None:
            predicates.append(predicate)
    return PairCandidatePlan(rule.rule_id, tuple(predicates))


def _candidate_predicate_for(
    operator_name: str,
    args: dict[str, object],
) -> PairCandidatePredicate | None:
    if operator_name in {
        "predicate.close_lateral_gap",
        "predicate.lateral_gap_between",
        "predicate.same_path_overlap",
        "predicate.pair_in_front",
        "predicate.low_ttc",
    }:
        return PairCandidatePredicate(operator_name, dict(args))
    return None


def _rotate(dx: float, dy: float, heading: float) -> tuple[float, float]:
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    return dx * cos_h + dy * sin_h, -dx * sin_h + dy * cos_h


def _pair_order_key(subject_id, order: dict[str, int]) -> tuple[int, int, str]:
    if not isinstance(subject_id, str) or ":" not in subject_id:
        return (10**9, 10**9, str(subject_id))
    ego_id, other_id = subject_id.split(":", 1)
    return (
        order.get(ego_id, 10**9),
        order.get(other_id, 10**9),
        subject_id,
    )
