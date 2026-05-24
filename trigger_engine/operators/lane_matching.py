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

    ax, ay = agent.center.x, agent.center.y
    best: LaneMatch | None = None
    best_score = float("inf")

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
            seg_dx, seg_dy = x1 - x0, y1 - y0
            seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy
            if seg_len_sq == 0:
                continue

            t = ((ax - x0) * seg_dx + (ay - y0) * seg_dy) / seg_len_sq
            t = max(0.0, min(1.0, t))

            proj_x = x0 + t * seg_dx
            proj_y = y0 + t * seg_dy
            lat = math.sqrt((ax - proj_x) ** 2 + (ay - proj_y) ** 2)

            seg_heading = math.atan2(seg_dy, seg_dx)
            heading_delta = abs(agent.heading - seg_heading)
            if heading_delta > math.pi:
                heading_delta = 2 * math.pi - heading_delta

            if lat <= max_lateral_m and heading_delta <= max_heading_delta_rad:
                score = lat + heading_weight_m_per_rad * heading_delta
                if score < best_score:
                    props = feature.properties or {}
                    best_score = score
                    best = LaneMatch(
                        lane_id=feature.feature_id,
                        lateral_m=lat,
                        longitudinal_s_m=cumulative + t * math.sqrt(seg_len_sq),
                        heading_delta_rad=heading_delta,
                        speed_limit_mph=props.get("speed_limit_mph"),
                        lane_type=props.get("lane_type"),
                    )

            cumulative += math.sqrt(seg_len_sq)

    return best
