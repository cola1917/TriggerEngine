from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LaneMatch:
    lane_id: int
    lateral_m: float
    longitudinal_s_m: float
    heading_delta_rad: float
    speed_limit_mph: float | None
    lane_type: str | None


@dataclass(frozen=True)
class _LaneSegment:
    order: int
    lane_id: int
    feature: object
    x0: float
    y0: float
    x1: float
    y1: float
    dx: float
    dy: float
    len_sq: float
    length: float
    cumulative_s_m: float


class LaneSegmentIndex:
    def __init__(self, map_features: dict, cell_size_m: float = 10.0) -> None:
        self.cell_size_m = cell_size_m
        self._cells: dict[tuple[int, int], list[_LaneSegment]] = {}
        self._segments: list[_LaneSegment] = []
        order = 0

        for feature in map_features.values():
            if feature.feature_type != "lane":
                continue
            polyline = feature.polyline
            if len(polyline) < 2:
                continue

            cumulative = 0.0
            for i in range(len(polyline) - 1):
                x0, y0 = polyline[i].x, polyline[i].y
                x1, y1 = polyline[i + 1].x, polyline[i + 1].y
                dx, dy = x1 - x0, y1 - y0
                len_sq = dx * dx + dy * dy
                if len_sq == 0:
                    continue
                length = math.sqrt(len_sq)
                segment = _LaneSegment(
                    order=order,
                    lane_id=feature.feature_id,
                    feature=feature,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    dx=dx,
                    dy=dy,
                    len_sq=len_sq,
                    length=length,
                    cumulative_s_m=cumulative,
                )
                self._segments.append(segment)
                self._index_segment(segment)
                order += 1
                cumulative += length

    def candidates(self, x: float, y: float, radius_m: float) -> list[_LaneSegment]:
        if not self._segments:
            return []

        min_cx, min_cy = self._cell(x - radius_m, y - radius_m)
        max_cx, max_cy = self._cell(x + radius_m, y + radius_m)
        seen: set[int] = set()
        candidates = []
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                for segment in self._cells.get((cx, cy), ()):
                    if segment.order in seen:
                        continue
                    seen.add(segment.order)
                    candidates.append(segment)
        candidates.sort(key=lambda segment: segment.order)
        return candidates

    def _index_segment(self, segment: _LaneSegment) -> None:
        min_cx, min_cy = self._cell(min(segment.x0, segment.x1), min(segment.y0, segment.y1))
        max_cx, max_cy = self._cell(max(segment.x0, segment.x1), max(segment.y0, segment.y1))
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                self._cells.setdefault((cx, cy), []).append(segment)

    def _cell(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / self.cell_size_m), math.floor(y / self.cell_size_m)


def _score_segment(
    agent,
    segment: _LaneSegment,
    *,
    max_lateral_m: float,
    max_heading_delta_rad: float,
    heading_weight_m_per_rad: float,
) -> LaneMatch | None:
    ax, ay = agent.center.x, agent.center.y
    t = ((ax - segment.x0) * segment.dx + (ay - segment.y0) * segment.dy) / segment.len_sq
    t = max(0.0, min(1.0, t))

    proj_x = segment.x0 + t * segment.dx
    proj_y = segment.y0 + t * segment.dy
    lat = math.sqrt((ax - proj_x) ** 2 + (ay - proj_y) ** 2)

    seg_heading = math.atan2(segment.dy, segment.dx)
    heading_delta = abs(agent.heading - seg_heading)
    if heading_delta > math.pi:
        heading_delta = 2 * math.pi - heading_delta

    if lat > max_lateral_m or heading_delta > max_heading_delta_rad:
        return None

    props = segment.feature.properties or {}
    return LaneMatch(
        lane_id=segment.lane_id,
        lateral_m=lat,
        longitudinal_s_m=segment.cumulative_s_m + t * segment.length,
        heading_delta_rad=heading_delta,
        speed_limit_mph=props.get("speed_limit_mph"),
        lane_type=props.get("lane_type"),
    )


def match_agent_to_lane(
    agent,
    map_features: dict,
    *,
    max_lateral_m: float,
    max_heading_delta_rad: float,
    heading_weight_m_per_rad: float = 3.0,
) -> LaneMatch | None:
    if not agent.valid:
        return None

    best: LaneMatch | None = None
    best_score = float("inf")
    best_order = float("inf")

    index = LaneSegmentIndex(map_features)
    for segment in index.candidates(agent.center.x, agent.center.y, max_lateral_m):
        match = _score_segment(
            agent,
            segment,
            max_lateral_m=max_lateral_m,
            max_heading_delta_rad=max_heading_delta_rad,
            heading_weight_m_per_rad=heading_weight_m_per_rad,
        )
        if match is None:
            continue
        score = match.lateral_m + heading_weight_m_per_rad * match.heading_delta_rad
        if score < best_score or (score == best_score and segment.order < best_order):
            best_score = score
            best_order = segment.order
            best = match

    return best


def match_agent_to_lane_cached(
    context,
    agent,
    map_features: dict,
    *,
    max_lateral_m: float,
    max_heading_delta_rad: float,
    heading_weight_m_per_rad: float = 3.0,
) -> LaneMatch | None:
    cache = getattr(context, "lane_match_cache", None)
    if cache is None:
        return match_agent_to_lane(
            agent,
            map_features,
            max_lateral_m=max_lateral_m,
            max_heading_delta_rad=max_heading_delta_rad,
            heading_weight_m_per_rad=heading_weight_m_per_rad,
        )

    key = (
        agent.track_id,
        agent.timestamp_seconds,
        agent.center.x,
        agent.center.y,
        agent.heading,
        max_lateral_m,
        max_heading_delta_rad,
        heading_weight_m_per_rad,
    )
    if key not in cache:
        index = _lane_segment_index_for(context, map_features)
        cache[key] = match_agent_to_lane(
            agent,
            map_features,
            max_lateral_m=max_lateral_m,
            max_heading_delta_rad=max_heading_delta_rad,
            heading_weight_m_per_rad=heading_weight_m_per_rad,
        ) if index is None else _match_agent_to_lane_with_index(
            agent,
            index,
            max_lateral_m=max_lateral_m,
            max_heading_delta_rad=max_heading_delta_rad,
            heading_weight_m_per_rad=heading_weight_m_per_rad,
        )
    return cache[key]


def _lane_segment_index_for(context, map_features: dict) -> LaneSegmentIndex | None:
    index_cache = getattr(context, "lane_match_index_cache", None)
    if index_cache is None:
        return None
    key = ("lane_segment_index", id(map_features))
    if key not in index_cache:
        index_cache[key] = LaneSegmentIndex(map_features)
    return index_cache[key]


def _match_agent_to_lane_with_index(
    agent,
    index: LaneSegmentIndex,
    *,
    max_lateral_m: float,
    max_heading_delta_rad: float,
    heading_weight_m_per_rad: float,
) -> LaneMatch | None:
    if not agent.valid:
        return None

    best: LaneMatch | None = None
    best_score = float("inf")
    best_order = float("inf")
    for segment in index.candidates(agent.center.x, agent.center.y, max_lateral_m):
        match = _score_segment(
            agent,
            segment,
            max_lateral_m=max_lateral_m,
            max_heading_delta_rad=max_heading_delta_rad,
            heading_weight_m_per_rad=heading_weight_m_per_rad,
        )
        if match is None:
            continue
        score = match.lateral_m + heading_weight_m_per_rad * match.heading_delta_rad
        if score < best_score or (score == best_score and segment.order < best_order):
            best_score = score
            best_order = segment.order
            best = match
    return best
