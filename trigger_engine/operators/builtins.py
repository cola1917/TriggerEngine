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


def _agent_in_frame(aligned_frame, track_id: int):
    return next(
        (
            agent
            for agent in aligned_frame.frame.agent_states
            if agent.track_id == track_id and agent.valid
        ),
        None,
    )


def _agent_speed_change_over_window(context, frame, track_id: int, window_seconds: float):
    if context is None:
        return None
    current = _agent_in_frame(frame, track_id)
    if current is None:
        return None

    start_time = frame.frame.timestamp_seconds - window_seconds
    earliest = None
    for aligned_frame in context.input_frames:
        ts = aligned_frame.frame.timestamp_seconds
        if ts < start_time or ts > frame.frame.timestamp_seconds:
            continue
        candidate = _agent_in_frame(aligned_frame, track_id)
        if candidate is not None:
            earliest = (aligned_frame, candidate)
            break
    if earliest is None:
        return None

    start_frame, start_agent = earliest
    dt = frame.frame.timestamp_seconds - start_frame.frame.timestamp_seconds
    if dt <= 0:
        return None

    start_speed = _speed(start_agent)
    end_speed = _speed(current)
    return {
        "start_frame_index": start_frame.frame.step_index,
        "end_frame_index": frame.frame.step_index,
        "window_seconds": dt,
        "start_speed_mps": start_speed,
        "end_speed_mps": end_speed,
        "speed_delta_mps": end_speed - start_speed,
        "acceleration_mps2": (end_speed - start_speed) / dt,
    }


def _red_light_stop_ahead(frame, subject, max_longitudinal_m: float, max_lateral_m: float):
    stop_states = {"stop", "arrow_stop"}
    best = None
    for tl in frame.frame.traffic_lights:
        if tl.state not in stop_states or tl.stop_point is None:
            continue
        dx = tl.stop_point.x - subject.ego.center.x
        dy = tl.stop_point.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        if lon < 0.0 or lon > max_longitudinal_m or abs(lat) > max_lateral_m:
            continue
        if best is None or lon < best["red_light_stop_longitudinal_m"]:
            best = {
                "red_light_lane_id": tl.lane_id,
                "red_light_state": tl.state,
                "red_light_stop_longitudinal_m": lon,
                "red_light_stop_lateral_m": lat,
            }
    return best


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


class PairOtherTypeInOperator:
    name = "predicate.pair_other_type_in"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        types = set(args["object_types"])
        value = subject.ego.valid and subject.other.valid and subject.other.object_type in types
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"other_type": subject.other.object_type, "object_types": sorted(types)},
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


class PairOtherSpeedAboveOperator:
    name = "predicate.pair_other_speed_above"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {},
            )
        threshold = args["threshold_mps"]
        speed = _speed(subject.other)
        value = speed > threshold
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {"other_speed_mps": speed, "threshold_mps": threshold},
        )


class PairEgoHardBrakingOperator:
    name = "predicate.pair_ego_hard_braking"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )

        allowed_types = set(args.get("other_types", ("vehicle", "pedestrian", "cyclist")))
        if subject.other.object_type not in allowed_types:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"other_type": subject.other.object_type},
            )

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        max_front = args.get("max_front_longitudinal_m", 40.0)
        max_lat = args.get("max_lateral_m", 4.0)
        if lon < 0.0 or lon > max_front or abs(lat) > max_lat:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"longitudinal_m": lon, "lateral_m": lat},
            )

        motion = _agent_speed_change_over_window(
            context, frame, subject.ego.track_id, args.get("window_seconds", 1.0)
        )
        if motion is None:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"longitudinal_m": lon, "lateral_m": lat},
            )

        max_acceleration = args["max_acceleration_mps2"]
        min_speed_drop = args.get("min_speed_drop_mps", 0.0)
        min_start_speed = args.get("min_start_speed_mps", 0.0)
        speed_drop = -motion["speed_delta_mps"]
        value = (
            motion["acceleration_mps2"] <= max_acceleration
            and speed_drop >= min_speed_drop
            and motion["start_speed_mps"] >= min_start_speed
        )
        red_stop = _red_light_stop_ahead(
            frame,
            subject,
            args.get("traffic_control_max_stop_longitudinal_m", max_front),
            args.get("traffic_control_max_stop_lateral_m", max_lat),
        )
        traffic_control_context = False
        if red_stop is not None:
            margin = args.get("traffic_control_target_margin_m", 5.0)
            traffic_control_context = red_stop["red_light_stop_longitudinal_m"] <= lon + margin
        risk_level = "medium" if traffic_control_context else "high"
        risk_reasons = ("traffic_control_stop",) if traffic_control_context else ()
        braking_category = "traffic_light" if traffic_control_context else "interaction"
        review_subtype = (
            "sdc_traffic_light_braking"
            if traffic_control_context
            else "sdc_interaction_braking"
        )
        metadata = {
            **motion,
            "speed_drop_mps": speed_drop,
            "longitudinal_m": lon,
            "lateral_m": lat,
            "other_type": subject.other.object_type,
            "traffic_control_context": traffic_control_context,
            "braking_category": braking_category,
            "review_subtype": review_subtype,
            "risk_level": risk_level if value else None,
            "risk_reasons": risk_reasons,
        }
        if red_stop is not None:
            metadata.update(red_stop)
        if value:
            event_metadata = {
                "risk_level": risk_level,
                "risk_reasons": risk_reasons,
                "traffic_control_context": traffic_control_context,
                "braking_category": braking_category,
                "review_subtype": review_subtype,
            }
            if red_stop is not None:
                event_metadata.update(red_stop)
            metadata["event_metadata"] = event_metadata
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value, metadata,
        )


class VruCloseInteractionOperator:
    name = "predicate.vru_close_interaction"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )
        vru_types = set(args.get("vru_types", ("pedestrian", "cyclist")))
        if subject.ego.object_type != "vehicle" or subject.other.object_type not in vru_types:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"ego_type": subject.ego.object_type, "other_type": subject.other.object_type},
            )

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        distance = math.sqrt(dx * dx + dy * dy)
        ego_speed = _speed(subject.ego)
        other_speed = _speed(subject.other)
        dvx = subject.ego.velocity_x - subject.other.velocity_x
        dvy = subject.ego.velocity_y - subject.other.velocity_y
        closing_speed, lateral_closing_speed = _rotate(dvx, dvy, subject.ego.heading)

        type_args = dict((args.get("type_thresholds") or {}).get(subject.other.object_type, {}))
        min_lon = args.get("min_longitudinal_m", -5.0)
        max_lon = type_args.get("max_longitudinal_m", args.get("max_longitudinal_m", 20.0))
        max_lat = type_args.get("max_lateral_m", args.get("max_lateral_m", 8.0))
        max_distance = type_args.get("max_distance_m", args.get("max_distance_m", 15.0))
        min_closing = type_args.get(
            "min_closing_speed_mps",
            args.get("min_closing_speed_mps", -float("inf")),
        )
        close_lateral = type_args.get("close_lateral_m", args.get("close_lateral_m", max_lat))
        wide_lateral_min_closing = type_args.get(
            "wide_lateral_min_closing_speed_mps",
            args.get("wide_lateral_min_closing_speed_mps", min_closing),
        )
        min_ego_speed = args.get("min_ego_speed_mps", 0.0)
        behind_close_distance = args.get("behind_close_distance_m", 0.0)
        behind_min_lon = args.get("behind_min_longitudinal_m", min_lon)

        ttc = float("inf")
        if lon > 0.0 and closing_speed > 0.0:
            ttc = lon / closing_speed

        motion = _agent_speed_change_over_window(
            context, frame, subject.ego.track_id, args.get("ego_response_window_seconds", 1.0)
        )
        ego_response = False
        if motion is not None:
            ego_response = (
                motion["acceleration_mps2"] <= args.get("ego_response_max_acceleration_mps2", -2.0)
                or -motion["speed_delta_mps"] >= args.get("ego_response_min_speed_drop_mps", 1.0)
            )

        longitudinal_ok = min_lon <= lon <= max_lon
        if lon < min_lon:
            longitudinal_ok = behind_min_lon <= lon < min_lon and distance <= behind_close_distance
        lateral_ok = abs(lat) <= close_lateral or (
            abs(lat) <= max_lat and closing_speed >= wide_lateral_min_closing
        )
        candidate_risk = (
            distance <= args.get("immediate_distance_m", 6.0)
            or ttc <= args.get("max_ttc_s", 4.0)
            or ego_response
        )
        risk_reasons = []
        high_close_lateral = type_args.get(
            "high_close_lateral_m",
            args.get("high_close_lateral_m", close_lateral),
        )
        high_ttc_lateral = type_args.get(
            "high_ttc_lateral_m",
            args.get("high_ttc_lateral_m", max_lat),
        )
        if (
            distance <= args.get("high_immediate_distance_m", 5.0)
            and abs(lat) <= high_close_lateral
        ):
            risk_reasons.append("immediate_distance")
        if ttc <= args.get("high_max_ttc_s", 3.0) and abs(lat) <= high_ttc_lateral:
            risk_reasons.append("low_ttc")
        if (
            ego_response
            and distance <= args.get("high_ego_response_max_distance_m", 10.0)
            and abs(lat) <= high_ttc_lateral
        ):
            risk_reasons.append("ego_response")
        risk_level = "high" if risk_reasons else "medium"
        value = (
            longitudinal_ok
            and lateral_ok
            and distance <= max_distance
            and ego_speed >= min_ego_speed
            and closing_speed >= min_closing
            and candidate_risk
        )
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {
                "longitudinal_m": lon,
                "lateral_m": lat,
                "distance_m": distance,
                "ego_speed_mps": ego_speed,
                "vru_speed_mps": other_speed,
                "closing_speed_mps": closing_speed,
                "lateral_closing_speed_mps": lateral_closing_speed,
                "ttc_s": ttc,
                "longitudinal_ok": longitudinal_ok,
                "lateral_ok": lateral_ok,
                "candidate_risk": candidate_risk,
                "risk_level": risk_level if value else None,
                "risk_reasons": tuple(risk_reasons),
                "ego_response": ego_response,
                "ego_acceleration_mps2": motion["acceleration_mps2"] if motion is not None else None,
                "ego_speed_delta_mps": motion["speed_delta_mps"] if motion is not None else None,
                "max_distance_m": max_distance,
                "max_lateral_m": max_lat,
                "close_lateral_m": close_lateral,
                "high_close_lateral_m": high_close_lateral,
                "high_ttc_lateral_m": high_ttc_lateral,
                "min_closing_speed_mps": min_closing,
                "vru_type": subject.other.object_type,
                "event_metadata": {
                    "risk_level": risk_level,
                    "risk_reasons": tuple(risk_reasons),
                } if value else {},
            },
        )


def _agent_low_speed_frames_over_window(context, frame, track_id: int, window_seconds: float, max_speed_mps: float):
    if context is None:
        return None
    start_time = frame.frame.timestamp_seconds - window_seconds
    frames = []
    for aligned_frame in context.input_frames:
        ts = aligned_frame.frame.timestamp_seconds
        if ts < start_time or ts > frame.frame.timestamp_seconds:
            continue
        agent = _agent_in_frame(aligned_frame, track_id)
        if agent is None:
            continue
        speed = _speed(agent)
        frames.append((aligned_frame, agent, speed, speed <= max_speed_mps))
    if not frames:
        return None
    low_speed_count = sum(1 for _, _, _, is_low in frames if is_low)
    return {
        "observed_frame_count": len(frames),
        "low_speed_frame_count": low_speed_count,
        "window_seconds": frames[-1][0].frame.timestamp_seconds - frames[0][0].frame.timestamp_seconds,
        "max_observed_speed_mps": max(speed for _, _, speed, _ in frames),
        "matched_frame_indices": [aligned_frame.frame.step_index for aligned_frame, _, _, _ in frames],
    }


class SdcBlockedUnableToProceedOperator:
    name = "predicate.sdc_blocked_unable_to_proceed"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if args.get("only_current_frame", False) and (
            frame.visibility != "current" or frame.frame.phase != "current"
        ):
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"visibility": frame.visibility, "phase": frame.frame.phase},
            )
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )
        blocker_types = set(args.get("blocker_types", ("vehicle", "pedestrian", "cyclist", "unknown")))
        if subject.ego.object_type != "vehicle" or subject.other.object_type not in blocker_types:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"ego_type": subject.ego.object_type, "blocker_type": subject.other.object_type},
            )

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        distance = math.sqrt(dx * dx + dy * dy)
        min_front = args.get("min_front_longitudinal_m", 1.0)
        max_front = args.get("max_front_longitudinal_m", 12.0)
        max_lateral = args.get("max_lateral_m", 2.5)
        if lon < min_front or lon > max_front or abs(lat) > max_lateral:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"longitudinal_m": lon, "lateral_m": lat, "distance_m": distance},
            )

        ego_speed = _speed(subject.ego)
        blocker_speed = _speed(subject.other)
        max_ego_speed = args.get("max_ego_speed_mps", 0.4)
        max_blocker_speed = args.get("max_blocker_speed_mps", 0.8)
        if ego_speed > max_ego_speed or blocker_speed > max_blocker_speed:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    "ego_speed_mps": ego_speed,
                    "blocker_speed_mps": blocker_speed,
                    "longitudinal_m": lon,
                    "lateral_m": lat,
                },
            )

        stop_window = _agent_low_speed_frames_over_window(
            context,
            frame,
            subject.ego.track_id,
            args.get("window_seconds", 1.0),
            max_ego_speed,
        )
        if stop_window is None:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"ego_speed_mps": ego_speed, "blocker_speed_mps": blocker_speed},
            )
        min_recent_motion = args.get("min_recent_ego_motion_mps", 0.0)
        if stop_window["max_observed_speed_mps"] < min_recent_motion:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    **stop_window,
                    "ego_speed_mps": ego_speed,
                    "blocker_speed_mps": blocker_speed,
                    "longitudinal_m": lon,
                    "lateral_m": lat,
                    "distance_m": distance,
                    "blocker_type": subject.other.object_type,
                    "blocked_category": "static_follow_stop",
                    "min_recent_ego_motion_mps": min_recent_motion,
                },
            )
        min_stopped_frames = args.get("min_stopped_frames", 6)
        if stop_window["low_speed_frame_count"] < min_stopped_frames:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    **stop_window,
                    "ego_speed_mps": ego_speed,
                    "blocker_speed_mps": blocker_speed,
                    "longitudinal_m": lon,
                    "lateral_m": lat,
                },
            )

        red_stop = _red_light_stop_ahead(
            frame,
            subject,
            args.get("traffic_control_max_stop_longitudinal_m", max_front + 5.0),
            args.get("traffic_control_max_stop_lateral_m", max_lateral),
        )
        if red_stop is not None:
            metadata = {
                **stop_window,
                **red_stop,
                "ego_speed_mps": ego_speed,
                "blocker_speed_mps": blocker_speed,
                "longitudinal_m": lon,
                "lateral_m": lat,
                "distance_m": distance,
                "blocker_type": subject.other.object_type,
                "traffic_control_context": True,
                "blocked_category": "traffic_control_stop",
                "review_subtype": "traffic_control_stop",
                "risk_level": "medium",
                "risk_reasons": ("traffic_control_stop",),
            }
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                metadata,
            )

        queue_like_count = 0
        if subject.other.object_type == "vehicle":
            queue_max_front = args.get("queue_max_front_longitudinal_m", max_front + 10.0)
            queue_max_lateral = args.get("queue_max_lateral_m", max_lateral)
            for other in frame.frame.agent_states:
                if not other.valid or other.track_id in (subject.ego.track_id, subject.other.track_id):
                    continue
                if other.object_type != "vehicle" or _speed(other) > max_blocker_speed:
                    continue
                odx = other.center.x - subject.ego.center.x
                ody = other.center.y - subject.ego.center.y
                other_lon, other_lat = _rotate(odx, ody, subject.ego.heading)
                if min_front <= other_lon <= queue_max_front and abs(other_lat) <= queue_max_lateral:
                    queue_like_count += 1
        min_queue_vehicles = args.get("min_queue_vehicle_count", 2)
        queue_vehicle_count = queue_like_count + 1
        if queue_vehicle_count >= min_queue_vehicles:
            metadata = {
                **stop_window,
                "ego_speed_mps": ego_speed,
                "blocker_speed_mps": blocker_speed,
                "longitudinal_m": lon,
                "lateral_m": lat,
                "distance_m": distance,
                "blocker_type": subject.other.object_type,
                "queue_vehicle_count": queue_vehicle_count,
                "traffic_control_context": False,
                "blocked_category": "queue_like_stop",
                "review_subtype": "queue_like_stop",
                "risk_level": "medium",
                "risk_reasons": ("queue_like_stop",),
            }
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                metadata,
            )

        subtype_by_type = {
            "vehicle": "blocked_by_vehicle",
            "pedestrian": "blocked_by_vru",
            "cyclist": "blocked_by_vru",
        }
        review_subtype = subtype_by_type.get(subject.other.object_type, "blocked_by_unknown")
        metadata = {
            **stop_window,
            "ego_speed_mps": ego_speed,
            "blocker_speed_mps": blocker_speed,
            "longitudinal_m": lon,
            "lateral_m": lat,
            "distance_m": distance,
            "blocker_type": subject.other.object_type,
            "blocker_track_id": subject.other.track_id,
            "queue_vehicle_count": queue_like_count + (1 if subject.other.object_type == "vehicle" else 0),
            "traffic_control_context": False,
            "blocked_category": "blocked",
            "review_subtype": review_subtype,
            "risk_level": "high",
            "risk_reasons": ("front_blocker", "sustained_ego_stop"),
            "event_metadata": {
                "risk_level": "high",
                "risk_reasons": ("front_blocker", "sustained_ego_stop"),
                "traffic_control_context": False,
                "blocked_category": "blocked",
                "review_subtype": review_subtype,
                "blocker_type": subject.other.object_type,
                "blocker_track_id": subject.other.track_id,
            },
        }
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            True,
            metadata,
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


def _agent_heading_change_after(context, frame, track_id: int, horizon_seconds: float) -> float | None:
    if context is None:
        return None
    start = None
    end = None
    start_time = frame.frame.timestamp_seconds
    max_time = start_time + horizon_seconds + 1e-6
    for aligned_frame in tuple(context.input_frames) + tuple(context.future_frames):
        ts = aligned_frame.frame.timestamp_seconds
        if ts < start_time or ts > max_time:
            continue
        agent = next(
            (a for a in aligned_frame.frame.agent_states if a.track_id == track_id and a.valid),
            None,
        )
        if agent is None:
            continue
        if start is None:
            start = agent.heading
        end = agent.heading
    if start is None or end is None:
        return None
    return _heading_delta(start, end)


def _future_heading_change_exceeds(context, frame, track_id: int, args, *, prefix: str = ""):
    max_change = args.get(f"{prefix}max_future_heading_change_rad")
    if max_change is None:
        return None, False
    horizon = args.get(f"{prefix}future_heading_horizon_seconds", 2.0)
    heading_change = _agent_heading_change_after(context, frame, track_id, horizon)
    return heading_change, heading_change is not None and heading_change > max_change


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

        future_heading_change, future_heading_rejected = _future_heading_change_exceeds(
            context, frame, subject.track_id, args
        )
        if future_heading_rejected:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"future_heading_change_rad": future_heading_change},
            )
        extended_future_heading_change, extended_future_heading_rejected = (
            _future_heading_change_exceeds(context, frame, subject.track_id, args, prefix="extended_")
        )
        if extended_future_heading_rejected:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"extended_future_heading_change_rad": extended_future_heading_change},
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
                        "future_heading_change_rad": future_heading_change,
                        "extended_future_heading_change_rad": extended_future_heading_change,
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

        future_heading_change, future_heading_rejected = _future_heading_change_exceeds(
            context, frame, subject.track_id, args
        )
        if future_heading_rejected:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"future_heading_change_rad": future_heading_change},
            )
        extended_future_heading_change, extended_future_heading_rejected = (
            _future_heading_change_exceeds(context, frame, subject.track_id, args, prefix="extended_")
        )
        if extended_future_heading_rejected:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"extended_future_heading_change_rad": extended_future_heading_change},
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
                                "future_heading_change_rad": future_heading_change,
                                "extended_future_heading_change_rad": extended_future_heading_change,
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

        from .lane_matching import match_agent_to_lane_cached

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
            m = match_agent_to_lane_cached(
                context, agent, context.map_features,
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

        from .lane_matching import match_agent_to_lane_cached

        window_seconds = args["window_seconds"]
        min_changes = args["min_lane_changes"]
        max_lateral = args["max_lateral_m"]
        max_heading = args["max_heading_delta_rad"]
        min_speed = args.get("min_speed_mps", 0.0)
        min_stable_frames = args.get("min_stable_frames", 2)
        min_lateral_displacement = args.get("min_lateral_displacement_m", 0.0)

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
            m = match_agent_to_lane_cached(
                context, agent, context.map_features,
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
        lateral_displacement = 0.0
        if stable_runs:
            first_frame_index = stable_runs[0][0][0]
            last_frame_index = stable_runs[-1][-1][0]
            first_agent = None
            last_agent = None
            for af in context.input_frames:
                if af.frame.step_index not in (first_frame_index, last_frame_index):
                    continue
                agent = next(
                    (a for a in af.frame.agent_states if a.track_id == subject.track_id and a.valid),
                    None,
                )
                if agent is None:
                    continue
                if af.frame.step_index == first_frame_index:
                    first_agent = agent
                if af.frame.step_index == last_frame_index:
                    last_agent = agent
            if first_agent is not None and last_agent is not None:
                dx = last_agent.center.x - first_agent.center.x
                dy = last_agent.center.y - first_agent.center.y
                _, lateral_displacement = _rotate(dx, dy, first_agent.heading)
                lateral_displacement = abs(lateral_displacement)

        if lateral_displacement < min_lateral_displacement:
            return OperatorResult(
                self.name, "agent", subject.track_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    "lane_sequence": [m[2] for m in matched],
                    "stable_lane_sequence": stable_lane_sequence,
                    "lateral_displacement_m": lateral_displacement,
                    "min_lateral_displacement_m": min_lateral_displacement,
                    "matched_frame_indices": [m[0] for m in matched],
                    "matched_timestamps_seconds": [m[1] for m in matched],
                },
            )
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
                "lateral_displacement_m": lateral_displacement,
                "matched_frame_indices": [m[0] for m in matched],
                "matched_timestamps_seconds": [m[1] for m in matched],
            },
        )


class SdcLaneChangeConflictOperator:
    name = "predicate.sdc_lane_change_conflict"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        if not subject.ego.valid or not subject.other.valid:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )
        if context is None or not context.map_features:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {},
            )
        if subject.ego.object_type != "vehicle" or subject.other.object_type != "vehicle":
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {"ego_type": subject.ego.object_type, "other_type": subject.other.object_type},
            )

        dx = subject.other.center.x - subject.ego.center.x
        dy = subject.other.center.y - subject.ego.center.y
        lon, lat = _rotate(dx, dy, subject.ego.heading)
        max_front = args.get("max_front_longitudinal_m", 25.0)
        max_behind = args.get("max_behind_longitudinal_m", 20.0)
        max_lateral = args.get("max_lateral_m", 3.0)
        if lon > max_front or lon < -max_behind or abs(lat) > max_lateral:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"longitudinal_m": lon, "lateral_m": lat},
            )

        other_speed = _speed(subject.other)
        min_target_speed = args.get("min_target_speed_mps", 0.0)
        if other_speed < min_target_speed:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    "other_speed_mps": other_speed,
                    "min_target_speed_mps": min_target_speed,
                    "longitudinal_m": lon,
                    "lateral_m": lat,
                },
            )

        from .lane_matching import match_agent_to_lane_cached

        window_seconds = args.get("window_seconds", 3.0)
        max_lane_lateral = args.get("max_lane_lateral_m", 1.8)
        max_heading = args.get("max_heading_delta_rad", 0.7)
        min_lateral_displacement = args.get("min_lateral_displacement_m", 1.5)
        current_time = frame.frame.timestamp_seconds

        ego_matches = []
        first_agent = None
        last_agent = None
        for af in context.input_frames:
            ts = af.frame.timestamp_seconds
            if ts < current_time - window_seconds or ts > current_time:
                continue
            ego_agent = _agent_in_frame(af, subject.ego.track_id)
            if ego_agent is None:
                continue
            match = match_agent_to_lane_cached(
                context,
                ego_agent,
                context.map_features,
                max_lateral_m=max_lane_lateral,
                max_heading_delta_rad=max_heading,
            )
            if match is None:
                continue
            if first_agent is None:
                first_agent = ego_agent
            last_agent = ego_agent
            ego_matches.append((af.frame.step_index, ts, match.lane_id))

        if len(ego_matches) < 2:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"matched_frames": len(ego_matches)},
            )
        previous_lane_id = ego_matches[0][2]
        current_lane_id = ego_matches[-1][2]
        if previous_lane_id == current_lane_id:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False, {"lane_sequence": [m[2] for m in ego_matches]},
            )

        lateral_displacement = 0.0
        if first_agent is not None and last_agent is not None:
            dx = last_agent.center.x - first_agent.center.x
            dy = last_agent.center.y - first_agent.center.y
            _, lateral_displacement = _rotate(dx, dy, first_agent.heading)
            lateral_displacement = abs(lateral_displacement)
        if lateral_displacement < min_lateral_displacement:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    "lane_sequence": [m[2] for m in ego_matches],
                    "lateral_displacement_m": lateral_displacement,
                },
            )

        other_match = match_agent_to_lane_cached(
            context,
            subject.other,
            context.map_features,
            max_lateral_m=args.get("target_lane_lateral_m", 2.2),
            max_heading_delta_rad=max_heading,
        )
        if other_match is not None and other_match.lane_id != current_lane_id:
            return OperatorResult(
                self.name, "agent_pair", subject.subject_id,
                frame.frame.step_index, frame.frame.timestamp_seconds,
                False,
                {
                    "ego_current_lane_id": current_lane_id,
                    "other_lane_id": other_match.lane_id,
                },
            )

        ego_forward_speed, _ = _rotate(subject.ego.velocity_x, subject.ego.velocity_y, subject.ego.heading)
        other_forward_speed, _ = _rotate(subject.other.velocity_x, subject.other.velocity_y, subject.ego.heading)
        max_ttc = args.get("max_ttc_s", 4.0)
        min_closing = args.get("min_closing_speed_mps", 0.5)
        ttc = float("inf")
        conflict_mode = None
        if lon >= 0:
            closing = ego_forward_speed - other_forward_speed
            if closing >= min_closing:
                ttc = lon / closing if closing > 0 else float("inf")
                if ttc <= max_ttc:
                    conflict_mode = "front_target"
        else:
            closing = other_forward_speed - ego_forward_speed
            gap = abs(lon)
            if closing >= min_closing:
                ttc = gap / closing if closing > 0 else float("inf")
                if ttc <= max_ttc:
                    conflict_mode = "rear_target"

        value = conflict_mode is not None
        return OperatorResult(
            self.name, "agent_pair", subject.subject_id,
            frame.frame.step_index, frame.frame.timestamp_seconds,
            value,
            {
                "previous_lane_id": previous_lane_id,
                "current_lane_id": current_lane_id,
                "other_lane_id": other_match.lane_id if other_match is not None else None,
                "lane_sequence": [m[2] for m in ego_matches],
                "lateral_displacement_m": lateral_displacement,
                "longitudinal_m": lon,
                "lateral_m": lat,
                "ego_forward_speed_mps": ego_forward_speed,
                "other_forward_speed_mps": other_forward_speed,
                "other_speed_mps": other_speed,
                "ttc_s": ttc,
                "conflict_mode": conflict_mode,
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

        from .lane_matching import match_agent_to_lane_cached

        max_lane_lat = args.get("max_lane_lateral_m", 1.8)
        max_lane_heading = args.get("max_heading_delta_rad", 0.7)
        fb_lat = args.get("fallback_max_lateral_m", 1.2)
        fb_heading = args.get("fallback_max_heading_delta_rad", 0.35)
        allow_fb = args.get("allow_fallback_without_map", True)

        map_features = getattr(context, "map_features", {}) if context is not None else {}

        ego_match = match_agent_to_lane_cached(
            context, subject.ego, map_features,
            max_lateral_m=max_lane_lat, max_heading_delta_rad=max_lane_heading,
        )
        other_match = match_agent_to_lane_cached(
            context, subject.other, map_features,
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
        PairOtherTypeInOperator(),
        PairInFrontOperator(),
        LowTtcOperator(),
        CloseLateralGapOperator(),
        LateralMotionTowardOperator(),
        HeadingConvergingOperator(),
        NearRedLightStopPointOperator(),
        LateralGapBetweenOperator(),
        SamePathOverlapOperator(),
        PairEgoSpeedAboveOperator(),
        PairOtherSpeedAboveOperator(),
        PairEgoHardBrakingOperator(),
        VruCloseInteractionOperator(),
        SdcBlockedUnableToProceedOperator(),
        RedLightBeforeStopLineOperator(),
        RedLightAfterStopLineOperator(),
        RedLightCrossingTransitionOperator(),
        SdcLaneChangedOperator(),
        SdcRepeatedLaneChangeOperator(),
        SdcLaneChangeConflictOperator(),
        SameLaneOrPathOperator(),
    ]
    for op in operators:
        try:
            registry.register(op)
        except OperatorRegistryError as exc:
            if "already registered" not in str(exc):
                raise
