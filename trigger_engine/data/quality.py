from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .frames import AgentState, ScenarioBundle, TrajectoryQualityIssue


@dataclass(frozen=True)
class TrajectoryQualityConfig:
    max_implied_speed_mps: float = 80.0
    max_implied_acceleration_mps2: float = 25.0
    max_heading_delta_rad: float = 1.6


class TrajectoryQualityAnnotator:
    def __init__(self, config: TrajectoryQualityConfig | None = None) -> None:
        self._config = config or TrajectoryQualityConfig()

    def annotate(self, bundle: ScenarioBundle) -> ScenarioBundle:
        issues: list[TrajectoryQualityIssue] = []
        previous_by_track: dict[int | str, AgentState] = {}
        previous_speed_by_track: dict[int | str, float] = {}
        previous_frame_by_track: dict[int | str, int] = {}

        for frame in bundle.frames:
            for agent in frame.agent_states:
                if not agent.valid:
                    previous_by_track.pop(agent.track_id, None)
                    previous_speed_by_track.pop(agent.track_id, None)
                    previous_frame_by_track.pop(agent.track_id, None)
                    continue
                previous = previous_by_track.get(agent.track_id)
                if previous is None:
                    previous_by_track[agent.track_id] = agent
                    previous_speed_by_track[agent.track_id] = _speed(agent)
                    previous_frame_by_track[agent.track_id] = frame.step_index
                    continue

                dt = agent.timestamp_seconds - previous.timestamp_seconds
                if dt <= 0.0:
                    previous_by_track[agent.track_id] = agent
                    previous_speed_by_track[agent.track_id] = _speed(agent)
                    previous_frame_by_track[agent.track_id] = frame.step_index
                    continue

                distance = _distance(previous, agent)
                implied_speed = distance / dt
                if implied_speed > self._config.max_implied_speed_mps:
                    issues.append(
                        self._issue(
                            "jump_speed",
                            agent,
                            frame.step_index,
                            implied_speed,
                            self._config.max_implied_speed_mps,
                            {
                                "previous_frame_index": previous_frame_by_track[agent.track_id],
                                "previous_timestamp_seconds": previous.timestamp_seconds,
                                "distance_m": distance,
                                "dt_seconds": dt,
                            },
                        )
                    )

                previous_speed = previous_speed_by_track.get(agent.track_id, _speed(previous))
                acceleration = abs((_speed(agent) - previous_speed) / dt)
                if acceleration > self._config.max_implied_acceleration_mps2:
                    issues.append(
                        self._issue(
                            "acceleration_jump",
                            agent,
                            frame.step_index,
                            acceleration,
                            self._config.max_implied_acceleration_mps2,
                            {
                                "previous_frame_index": previous_frame_by_track[agent.track_id],
                                "previous_timestamp_seconds": previous.timestamp_seconds,
                                "dt_seconds": dt,
                            },
                        )
                    )

                heading_delta = abs(_angle_delta(agent.heading, previous.heading))
                if heading_delta > self._config.max_heading_delta_rad:
                    issues.append(
                        self._issue(
                            "heading_jump",
                            agent,
                            frame.step_index,
                            heading_delta,
                            self._config.max_heading_delta_rad,
                            {
                                "previous_frame_index": previous_frame_by_track[agent.track_id],
                                "previous_timestamp_seconds": previous.timestamp_seconds,
                                "dt_seconds": dt,
                            },
                        )
                    )

                previous_by_track[agent.track_id] = agent
                previous_speed_by_track[agent.track_id] = _speed(agent)
                previous_frame_by_track[agent.track_id] = frame.step_index

        return replace(
            bundle,
            quality_issues=bundle.quality_issues + tuple(issues),
        )

    def _issue(
        self,
        issue_type: str,
        agent: AgentState,
        frame_index: int,
        value: float,
        threshold: float,
        metadata: dict[str, object],
    ) -> TrajectoryQualityIssue:
        return TrajectoryQualityIssue(
            issue_type=issue_type,
            track_id=agent.track_id,
            frame_index=frame_index,
            timestamp_seconds=agent.timestamp_seconds,
            value=value,
            threshold=threshold,
            metadata=metadata,
        )


def _speed(agent: AgentState) -> float:
    return math.hypot(agent.velocity_x, agent.velocity_y)


def _distance(first: AgentState, second: AgentState) -> float:
    return math.hypot(
        second.center.x - first.center.x,
        second.center.y - first.center.y,
    )


def _angle_delta(first: float, second: float) -> float:
    delta = first - second
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta < -math.pi:
        delta += 2.0 * math.pi
    return delta
