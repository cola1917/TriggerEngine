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


class PairEgoSpeedAboveOperator:
    name = "predicate.pair_ego_speed_above"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        threshold = args["threshold_mps"]
        speed = _speed(subject.ego)
        value = speed > threshold
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"ego_speed_mps": speed, "threshold_mps": threshold},
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


def _heading_delta(a: float, b: float) -> float:
    delta = abs(a - b)
    if delta > math.pi:
        delta = 2 * math.pi - delta
    return delta


def _lane_heading_change_from_stop(lane_polyline, stop_point, lookahead_m: float) -> float | None:
    if len(lane_polyline) < 2:
        return None

    best_index = None
    best_dist = float("inf")
    for i in range(len(lane_polyline) - 1):
        ax, ay = lane_polyline[i].x, lane_polyline[i].y
        bx, by = lane_polyline[i + 1].x, lane_polyline[i + 1].y
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        dist = math.sqrt((mx - stop_point.x) ** 2 + (my - stop_point.y) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_index = i

    if best_index is None:
        return None

    def segment_heading(index: int) -> float | None:
        ax, ay = lane_polyline[index].x, lane_polyline[index].y
        bx, by = lane_polyline[index + 1].x, lane_polyline[index + 1].y
        if ax == bx and ay == by:
            return None
        return math.atan2(by - ay, bx - ax)

    start_heading = segment_heading(best_index)
    if start_heading is None:
        return None

    walked = 0.0
    end_heading = start_heading
    for i in range(best_index, len(lane_polyline) - 1):
        ax, ay = lane_polyline[i].x, lane_polyline[i].y
        bx, by = lane_polyline[i + 1].x, lane_polyline[i + 1].y
        seg_len = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2)
        heading = segment_heading(i)
        if heading is not None:
            end_heading = heading
        walked += seg_len
        if walked >= lookahead_m:
            break

    return _heading_delta(start_heading, end_heading)


def _lane_ids(values) -> set[int]:
    return {int(value) for value in values or ()}


def _are_longitudinally_connected(map_features, from_lane_id: int, to_lane_id: int) -> bool:
    if from_lane_id == to_lane_id:
        return True
    from_lane = map_features.get(from_lane_id)
    to_lane = map_features.get(to_lane_id)
    if from_lane is None or to_lane is None:
        return False

    from_props = from_lane.properties or {}
    to_props = to_lane.properties or {}
    return (
        to_lane_id in _lane_ids(from_props.get("exit_lanes"))
        or from_lane_id in _lane_ids(to_props.get("entry_lanes"))
        or from_lane_id in _lane_ids(to_props.get("exit_lanes"))
        or to_lane_id in _lane_ids(from_props.get("entry_lanes"))
    )


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


class RedLightCrossingTransitionOperator:
    name = "predicate.red_light_crossing_transition"
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
        min_after = args["min_after_stop_line_m"]
        max_after = args["max_after_stop_line_m"]
        min_speed = args["min_speed_mps"]
        max_heading_delta = args["max_heading_delta_rad"]
        max_lane_heading_change = args.get("max_lane_heading_change_rad")
        lane_lookahead = args.get("lane_heading_lookahead_m", max_after)

        speed = _speed(subject)
        if speed < min_speed:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"speed_mps": speed},
            )

        if context is None:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )

        # Check current frame: SDC must be AFTER a red-light stop line
        current_reds = _find_red_light_and_lane(context, frame)
        for tl, (dir_x, dir_y) in current_reds:
            dx = subject.center.x - tl.stop_point.x
            dy = subject.center.y - tl.stop_point.y
            lon_after = dx * dir_x + dy * dir_y
            lat = -dx * dir_y + dy * dir_x
            lat_abs = abs(lat)

            heading_delta = abs(subject.heading - math.atan2(dir_y, dir_x))
            if heading_delta > math.pi:
                heading_delta = 2 * math.pi - heading_delta

            if not (
                lat_abs <= max_lat
                and min_after <= lon_after <= max_after
                and heading_delta <= max_heading_delta
            ):
                continue

            # Check earlier frames: SDC must have been BEFORE the SAME stop line
            current_lane_id = tl.lane_id
            if max_lane_heading_change is not None:
                lane = context.map_features.get(current_lane_id)
                if lane is not None:
                    lane_heading_change = _lane_heading_change_from_stop(
                        lane.polyline, tl.stop_point, lane_lookahead
                    )
                    if (
                        lane_heading_change is not None
                        and lane_heading_change > max_lane_heading_change
                    ):
                        continue
            for earlier in context.input_frames:
                if earlier.frame.step_index >= frame.frame.step_index:
                    break
                # Find the same agent in the earlier frame
                earlier_agent = None
                for a in earlier.frame.agent_states:
                    if a.track_id == subject.track_id and a.valid:
                        earlier_agent = a
                        break
                if earlier_agent is None:
                    continue
                for etl, (edir_x, edir_y) in _find_red_light_and_lane(context, earlier):
                    if etl.lane_id != current_lane_id:
                        continue
                    edx = earlier_agent.center.x - etl.stop_point.x
                    edy = earlier_agent.center.y - etl.stop_point.y
                    lon_before = edx * edir_x + edy * edir_y
                    lat_before = -edx * edir_y + edy * edir_x

                    # Agent must be near this lane in the earlier frame
                    if abs(lat_before) > max_lat:
                        continue

                    if -max_before <= lon_before < 0:
                        return OperatorResult(
                            self.name, "agent", subject.track_id,
                            frame.frame.step_index, frame.frame.timestamp_seconds,
                            True,
                            {
                                "lane_id": current_lane_id,
                                "longitudinal_before_m": lon_before,
                                "longitudinal_after_m": lon_after,
                                "lateral_m": lat,
                                "before_frame_index": earlier.frame.step_index,
                                "lane_heading_change_rad": (
                                    _lane_heading_change_from_stop(
                                        context.map_features[current_lane_id].polyline,
                                        tl.stop_point,
                                        lane_lookahead,
                                    )
                                    if max_lane_heading_change is not None
                                    else None
                                ),
                            },
                        )

        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            False, {},
        )


class SdcLaneChangedOperator:
    name = "predicate.sdc_lane_changed"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        if not subject.valid:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )
        if context is None or not context.map_features:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )

        from .lane_matching import match_agent_to_lane

        window_seconds = args["window_seconds"]
        max_lateral = args["max_lateral_m"]
        max_heading = args["max_heading_delta_rad"]
        min_speed = args.get("min_speed_mps", 0.0)

        speed = _speed(subject)
        if speed < min_speed:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"speed_mps": speed},
            )

        current_time = frame.frame.timestamp_seconds
        matched = []
        for af in context.input_frames:
            ts = af.frame.timestamp_seconds
            if ts < current_time - window_seconds or ts > current_time:
                continue
            agent = None
            for a in af.frame.agent_states:
                if a.track_id == subject.track_id and a.valid:
                    agent = a
                    break
            if agent is None:
                continue
            m = match_agent_to_lane(
                agent, context.map_features,
                max_lateral_m=max_lateral, max_heading_delta_rad=max_heading,
            )
            if m is not None:
                matched.append((af.frame.step_index, ts, m.lane_id))

        if len(matched) < 2:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"matched_frames": len(matched)},
            )

        for i in range(1, len(matched)):
            if matched[i][2] != matched[i - 1][2]:
                return OperatorResult(
                    self.name, "agent", subject.track_id,
                    frame.frame.step_index, frame.frame.timestamp_seconds,
                    True,
                    {
                        "previous_lane_id": matched[i - 1][2],
                        "current_lane_id": matched[i][2],
                        "previous_frame_index": matched[i - 1][0],
                        "current_frame_index": matched[i][0],
                        "lane_sequence": [m[2] for m in matched],
                    },
                )

        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            False, {"lane_sequence": [m[2] for m in matched]},
        )


class SdcRepeatedLaneChangeOperator:
    name = "predicate.sdc_repeated_lane_change"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        if not subject.valid:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )
        if context is None or not context.map_features:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )

        from .lane_matching import match_agent_to_lane

        window_seconds = args["window_seconds"]
        min_changes = args["min_lane_changes"]
        max_lateral = args["max_lateral_m"]
        max_heading = args["max_heading_delta_rad"]
        min_speed = args.get("min_speed_mps", 0.0)
        min_stable_frames = args.get("min_stable_frames", 2)

        speed = _speed(subject)
        if speed < min_speed:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"speed_mps": speed},
            )

        current_time = frame.frame.timestamp_seconds
        matched = []
        for af in context.input_frames:
            ts = af.frame.timestamp_seconds
            if ts < current_time - window_seconds or ts > current_time:
                continue
            agent = None
            for a in af.frame.agent_states:
                if a.track_id == subject.track_id and a.valid:
                    agent = a
                    break
            if agent is None:
                continue
            m = match_agent_to_lane(
                agent, context.map_features,
                max_lateral_m=max_lateral, max_heading_delta_rad=max_heading,
            )
            if m is not None:
                matched.append((af.frame.step_index, ts, m.lane_id))

        if len(matched) < 2:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"matched_frames": len(matched)},
            )

        stable_runs = []
        run_start = 0
        for i in range(1, len(matched) + 1):
            if i == len(matched) or matched[i][2] != matched[run_start][2]:
                run = matched[run_start:i]
                if len(run) >= min_stable_frames:
                    stable_runs.append(run)
                run_start = i

        stable_lane_sequence = [run[0][2] for run in stable_runs]
        topological_lane_sequence = []
        for lane_id in stable_lane_sequence:
            if not topological_lane_sequence:
                topological_lane_sequence.append(lane_id)
                continue
            previous_lane_id = topological_lane_sequence[-1]
            if _are_longitudinally_connected(
                context.map_features, previous_lane_id, lane_id
            ):
                topological_lane_sequence[-1] = lane_id
            else:
                topological_lane_sequence.append(lane_id)

        lane_change_count = 0
        for i in range(1, len(topological_lane_sequence)):
            if topological_lane_sequence[i] != topological_lane_sequence[i - 1]:
                lane_change_count += 1

        value = lane_change_count >= min_changes
        return OperatorResult(
            self.name, "agent", subject.track_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {
                "lane_sequence": [m[2] for m in matched],
                "stable_lane_sequence": stable_lane_sequence,
                "topological_lane_sequence": topological_lane_sequence,
                "lane_change_count": lane_change_count,
                "min_stable_frames": min_stable_frames,
                "matched_frame_indices": [m[0] for m in matched],
                "matched_timestamps_seconds": [m[1] for m in matched],
            },
        )


class SameLaneOrPathOperator:
    name = "predicate.same_lane_or_path"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )

        from .lane_matching import match_agent_to_lane

        max_lane_lat = args.get("max_lane_lateral_m", 1.8)
        max_lane_heading = args.get("max_heading_delta_rad", 0.7)
        fb_lat = args.get("fallback_max_lateral_m", 1.2)
        fb_heading = args.get("fallback_max_heading_delta_rad", 0.35)
        allow_fb = args.get("allow_fallback_without_map", True)

        map_features = getattr(context, "map_features", {}) if context is not None else {}

        ego_match = match_agent_to_lane(
            subject.ego, map_features,
            max_lateral_m=max_lane_lat, max_heading_delta_rad=max_lane_heading,
        )
        other_match = match_agent_to_lane(
            subject.other, map_features,
            max_lateral_m=max_lane_lat, max_heading_delta_rad=max_lane_heading,
        )

        if ego_match is not None and other_match is not None:
            same = ego_match.lane_id == other_match.lane_id
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                same,
                {
                    "mode": "lane",
                    "ego_lane_id": ego_match.lane_id,
                    "other_lane_id": other_match.lane_id,
                },
            )

        if map_features and (ego_match is None) != (other_match is None):
            matched_id = ego_match.lane_id if ego_match is not None else other_match.lane_id
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    "mode": "lane_mismatch",
                    "ego_lane_id": ego_match.lane_id if ego_match is not None else None,
                    "other_lane_id": other_match.lane_id if other_match is not None else None,
                },
            )

        if not allow_fb:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"mode": "no_fallback"},
            )

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        heading_delta = abs(subject.ego.heading - subject.other.heading)
        if heading_delta > math.pi:
            heading_delta = 2 * math.pi - heading_delta

        ok = abs(lat) <= fb_lat and heading_delta <= fb_heading
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            ok,
            {
                "mode": "fallback_path",
                "lateral_m": lat,
                "heading_delta_rad": heading_delta,
            },
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
        PairEgoSpeedAboveOperator(),
        RedLightBeforeStopLineOperator(),
        RedLightAfterStopLineOperator(),
        RedLightCrossingTransitionOperator(),
        SdcLaneChangedOperator(),
        SdcRepeatedLaneChangeOperator(),
        SameLaneOrPathOperator(),
    ]
    for op in operators:
        try:
            registry.register(op)
        except OperatorRegistryError as exc:
            if "already registered" not in str(exc):
                raise
