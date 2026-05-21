from __future__ import annotations

import math
from dataclasses import dataclass

from .base import OperatorResult
from .registry import OperatorRegistry, OperatorRegistryError


@dataclass(frozen=True)
class AgentPairSubject:
    ego: object
    other: object

    @property
    def subject_id(self) -> str:
        return f"{self.ego.track_id}:{self.other.track_id}"


def _speed(agent) -> float:
    return math.sqrt(agent.velocity_x ** 2 + agent.velocity_y ** 2)


def _rotate(dx: float, dy: float, heading: float) -> tuple[float, float]:
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    return dx * cos_h + dy * sin_h, -dx * sin_h + dy * cos_h


class TypeIsOperator:
    name = "predicate.type_is"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        value = subject.valid and subject.object_type == args["object_type"]
        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"object_type": args["object_type"]},
        )


class SpeedBelowOperator:
    name = "predicate.speed_below"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        speed = _speed(subject)
        value = subject.valid and speed < args["threshold_mps"]
        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"speed_mps": speed, "threshold_mps": args["threshold_mps"]},
        )


class SpeedAboveOperator:
    name = "predicate.speed_above"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        speed = _speed(subject)
        value = subject.valid and speed > args["threshold_mps"]
        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"speed_mps": speed, "threshold_mps": args["threshold_mps"]},
        )


class PairTypesAreOperator:
    name = "predicate.pair_types_are"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        ego_ok = (
            subject.ego.valid
            and (args.get("ego_type") is None or subject.ego.object_type == args["ego_type"])
        )
        other_ok = (
            subject.other.valid
            and (args.get("other_type") is None or subject.other.object_type == args["other_type"])
        )
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            ego_ok and other_ok,
            {"ego_type": subject.ego.object_type, "other_type": subject.other.object_type},
        )


class PairInFrontOperator:
    name = "predicate.pair_in_front"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        min_long = args.get("min_longitudinal_m", 0.0)
        max_lat = args.get("max_lateral_m", 4.0)

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        lat_abs = abs(lat)

        value = lon >= min_long and lat_abs <= max_lat
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"longitudinal_m": lon, "lateral_m": lat},
        )


class LowTtcOperator:
    name = "predicate.low_ttc"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        threshold_s = args["threshold_s"]
        max_lat = args.get("max_lateral_m", 4.0)
        min_closing = args.get("min_closing_speed_mps", 0.1)

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)

        if abs(lat) > max_lat:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"ttc_s": float("inf"), "lateral_m": lat},
            )

        dvx = subject.ego.velocity_x - subject.other.velocity_x
        dvy = subject.ego.velocity_y - subject.other.velocity_y
        closing_speed, _ = _rotate(dvx, dvy, subject.ego.heading)

        if closing_speed < min_closing or lon <= 0:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"ttc_s": float("inf"), "closing_speed_mps": closing_speed},
            )

        ttc = lon / closing_speed
        value = ttc < threshold_s
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"ttc_s": ttc, "closing_speed_mps": closing_speed, "longitudinal_m": lon},
        )


class CloseLateralGapOperator:
    name = "predicate.close_lateral_gap"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        max_lat = args["max_lateral_m"]
        max_long = args["max_longitudinal_m"]

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)

        value = abs(lat) <= max_lat and abs(lon) <= max_long
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"lateral_m": lat, "longitudinal_m": lon},
        )


class LateralMotionTowardOperator:
    name = "predicate.lateral_motion_toward"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        min_speed = args["min_lateral_speed_mps"]

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        _, lat = _rotate(dx, dy, subject.ego.heading)

        dvx = subject.other.velocity_x - subject.ego.velocity_x
        dvy = subject.other.velocity_y - subject.ego.velocity_y
        _, lat_vel = _rotate(dvx, dvy, subject.ego.heading)

        if lat > 0:
            moving_toward = lat_vel < -min_speed
        else:
            moving_toward = lat_vel > min_speed

        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            moving_toward,
            {"lateral_m": lat, "lateral_vel_mps": lat_vel},
        )


class HeadingConvergingOperator:
    name = "predicate.heading_converging"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        min_delta = args["min_heading_delta_rad"]
        max_delta = args["max_heading_delta_rad"]

        delta = abs(subject.ego.heading - subject.other.heading)
        if delta > math.pi:
            delta = 2 * math.pi - delta

        value = min_delta <= delta <= max_delta
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"heading_delta_rad": delta},
        )


class NearRedLightStopPointOperator:
    name = "predicate.near_red_light_stop_point"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        if not subject.valid:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        max_dist = args["max_distance_m"]
        stop_states = {"stop", "arrow_stop"}

        for tl in frame.frame.traffic_lights:
            if tl.state in stop_states and tl.stop_point is not None:
                dx = subject.center.x - tl.stop_point.x
                dy = subject.center.y - tl.stop_point.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= max_dist:
                    return OperatorResult(
                        self.name, "agent", subject.track_id,
                        frame.frame.step_index, frame.frame.timestamp_seconds,
                        True,
                        {"distance_to_stop_point": dist, "lane_id": tl.lane_id},
                    )

        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            False,
            {},
        )


class LateralGapBetweenOperator:
    name = "predicate.lateral_gap_between"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        min_lat = args["min_lateral_m"]
        max_lat = args["max_lateral_m"]
        max_long = args["max_longitudinal_m"]

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        lat_abs = abs(lat)

        value = min_lat <= lat_abs <= max_lat and abs(lon) <= max_long
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"lateral_m": lat, "longitudinal_m": lon},
        )


class SamePathOverlapOperator:
    name = "predicate.same_path_overlap"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        max_lat = args["max_lateral_m"]
        min_long = args.get("min_longitudinal_m", 0.0)
        max_long = args["max_longitudinal_m"]

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)

        value = abs(lat) <= max_lat and min_long <= lon <= max_long
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"lateral_m": lat, "longitudinal_m": lon},
        )


def _lane_direction_at_stop(lane_polyline, stop_point) -> tuple[float, float] | None:
    if len(lane_polyline) < 2:
        return None
    best_dist = float("inf")
    best_dir = None
    for i in range(len(lane_polyline) - 1):
        ax, ay = lane_polyline[i].x, lane_polyline[i].y
        bx, by = lane_polyline[i + 1].x, lane_polyline[i + 1].y
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        dist = math.sqrt((mx - stop_point.x) ** 2 + (my - stop_point.y) ** 2)
        if dist < best_dist:
            best_dist = dist
            dx, dy = bx - ax, by - ay
            length = math.sqrt(dx * dx + dy * dy)
            if length > 0:
                best_dir = (dx / length, dy / length)
    if best_dir is None:
        ax, ay = lane_polyline[0].x, lane_polyline[0].y
        bx, by = lane_polyline[-1].x, lane_polyline[-1].y
        dx, dy = bx - ax, by - ay
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            best_dir = (dx / length, dy / length)
    return best_dir


def _find_red_light_and_lane(context, frame):
    stop_states = {"stop", "arrow_stop"}
    map_features = getattr(context, "map_features", {}) if context is not None else {}
    results = []
    for tl in frame.frame.traffic_lights:
        if tl.state in stop_states and tl.stop_point is not None:
            lane = map_features.get(tl.lane_id)
            if lane is None or not lane.polyline:
                continue
            direction = _lane_direction_at_stop(lane.polyline, tl.stop_point)
            if direction is None:
                continue
            results.append((tl, direction))
    return results


class RedLightBeforeStopLineOperator:
    name = "predicate.red_light_before_stop_line"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        if not subject.valid:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )

        max_lat = args["max_lateral_m"]
        max_before = args["max_before_stop_line_m"]
        min_speed = args["min_speed_mps"]
        max_heading_delta = args["max_heading_delta_rad"]

        speed = _speed(subject)
        if speed < min_speed:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"speed_mps": speed},
            )

        for tl, (dir_x, dir_y) in _find_red_light_and_lane(context, frame):
            dx = subject.center.x - tl.stop_point.x
            dy = subject.center.y - tl.stop_point.y
            lon = dx * dir_x + dy * dir_y
            lat = -dx * dir_y + dy * dir_x
            lat_abs = abs(lat)

            heading_delta = abs(subject.heading - math.atan2(dir_y, dir_x))
            if heading_delta > math.pi:
                heading_delta = 2 * math.pi - heading_delta

            if (
                lat_abs <= max_lat
                and -max_before <= lon < 0
                and heading_delta <= max_heading_delta
            ):
                return OperatorResult(
                    self.name, "agent", subject.track_id,
                    frame.frame.step_index, frame.frame.timestamp_seconds,
                    True,
                    {
                        "lane_id": tl.lane_id,
                        "longitudinal_m": lon,
                        "lateral_m": lat,
                        "speed_mps": speed,
                        "heading_delta_rad": heading_delta,
                    },
                )

        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            False, {},
        )


class RedLightAfterStopLineOperator:
    name = "predicate.red_light_after_stop_line"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        if not subject.valid:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )

        max_lat = args["max_lateral_m"]
        min_after = args["min_after_stop_line_m"]
        max_after = args["max_after_stop_line_m"]
        min_speed = args["min_speed_mps"]
        max_heading_delta = args["max_heading_delta_rad"]

        speed = _speed(subject)
        if speed < min_speed:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"speed_mps": speed},
            )

        for tl, (dir_x, dir_y) in _find_red_light_and_lane(context, frame):
            dx = subject.center.x - tl.stop_point.x
            dy = subject.center.y - tl.stop_point.y
            lon = dx * dir_x + dy * dir_y
            lat = -dx * dir_y + dy * dir_x
            lat_abs = abs(lat)

            heading_delta = abs(subject.heading - math.atan2(dir_y, dir_x))
            if heading_delta > math.pi:
                heading_delta = 2 * math.pi - heading_delta

            if (
                lat_abs <= max_lat
                and min_after <= lon <= max_after
                and heading_delta <= max_heading_delta
            ):
                return OperatorResult(
                    self.name, "agent", subject.track_id,
                    frame.frame.step_index, frame.frame.timestamp_seconds,
                    True,
                    {
                        "lane_id": tl.lane_id,
                        "longitudinal_m": lon,
                        "lateral_m": lat,
                        "speed_mps": speed,
                        "heading_delta_rad": heading_delta,
                    },
                )

        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            False, {},
        )


def register_builtin_operators(registry: OperatorRegistry) -> None:
    operators = [
        TypeIsOperator(),
        SpeedBelowOperator(),
        SpeedAboveOperator(),
        PairTypesAreOperator(),
        PairInFrontOperator(),
        LowTtcOperator(),
        CloseLateralGapOperator(),
        LateralMotionTowardOperator(),
        HeadingConvergingOperator(),
        NearRedLightStopPointOperator(),
        LateralGapBetweenOperator(),
        SamePathOverlapOperator(),
        RedLightBeforeStopLineOperator(),
        RedLightAfterStopLineOperator(),
    ]
    for op in operators:
        try:
            registry.register(op)
        except OperatorRegistryError as exc:
            if "already registered" not in str(exc):
                raise
