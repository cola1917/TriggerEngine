from __future__ import annotations

from .frames import (
    AgentState,
    Frame,
    MapFeature,
    Point3D,
    PredictionTarget,
    ScenarioBundle,
    TrafficLightState,
)
from .validation import DataAdapterError, validate_scenario


_OBJECT_TYPE_MAP = {
    0: "unset",
    1: "vehicle",
    2: "pedestrian",
    3: "cyclist",
    4: "other",
}

_LANE_STATE_MAP = {
    0: "unknown",
    1: "arrow_stop",
    2: "arrow_caution",
    3: "arrow_go",
    4: "stop",
    5: "caution",
    6: "go",
    7: "flashing_stop",
    8: "flashing_caution",
}

_DIFFICULTY_MAP = {
    0: "none",
    1: "level_1",
    2: "level_2",
}

_ROAD_LINE_TYPE_MAP = {
    0: "unknown",
    1: "broken_single_white",
    2: "solid_single_white",
    3: "solid_double_white",
    4: "broken_single_yellow",
    5: "broken_double_yellow",
    6: "solid_single_yellow",
    7: "solid_double_yellow",
    8: "passing_double_yellow",
}

_ROAD_EDGE_TYPE_MAP = {
    0: "unknown",
    1: "road_edge_boundary",
    2: "road_edge_median",
}

_LANE_TYPE_MAP = {
    0: "undefined",
    1: "freeway",
    2: "surface_street",
    3: "bike_lane",
}


def _normalize_object_type(raw: int) -> str:
    return _OBJECT_TYPE_MAP.get(raw, "unknown")


def _normalize_lane_state(raw: int) -> str:
    return _LANE_STATE_MAP.get(raw, "unknown")


def _normalize_difficulty(raw: int) -> str:
    return _DIFFICULTY_MAP.get(raw, "unknown")


def _to_point3d(proto) -> Point3D:
    return Point3D(proto.x, proto.y, proto.z)


def _convert_lane(lane) -> MapFeature:
    polyline = tuple(_to_point3d(p) for p in lane.polyline)
    properties: dict[str, object] = {
        "lane_type": _LANE_TYPE_MAP.get(lane.type, "unknown"),
        "speed_limit_mph": lane.speed_limit_mph,
        "interpolating": lane.interpolating,
        "entry_lanes": tuple(lane.entry_lanes),
        "exit_lanes": tuple(lane.exit_lanes),
    }
    return MapFeature(
        0,
        "lane",
        polyline,
        (),
        properties,
    )


def _convert_road_line(road_line) -> MapFeature:
    polyline = tuple(_to_point3d(p) for p in road_line.polyline)
    return MapFeature(
        0,
        "road_line",
        polyline,
        (),
        {"road_line_type": _ROAD_LINE_TYPE_MAP.get(road_line.type, "unknown")},
    )


def _convert_road_edge(road_edge) -> MapFeature:
    polyline = tuple(_to_point3d(p) for p in road_edge.polyline)
    return MapFeature(
        0,
        "road_edge",
        polyline,
        (),
        {"road_edge_type": _ROAD_EDGE_TYPE_MAP.get(road_edge.type, "unknown")},
    )


def _convert_crosswalk(crosswalk) -> MapFeature:
    polygon = tuple(_to_point3d(p) for p in crosswalk.polygon)
    return MapFeature(
        0,
        "crosswalk",
        (),
        polygon,
        {},
    )


def _convert_speed_bump(speed_bump) -> MapFeature:
    polygon = tuple(_to_point3d(p) for p in speed_bump.polygon)
    return MapFeature(
        0,
        "speed_bump",
        (),
        polygon,
        {},
    )


def _convert_stop_sign(stop_sign) -> MapFeature:
    position = _to_point3d(stop_sign.position)
    return MapFeature(
        0,
        "stop_sign",
        (),
        (),
        {"position": position, "lane_ids": tuple(stop_sign.lane)},
    )


def _convert_driveway(driveway) -> MapFeature:
    polygon = tuple(_to_point3d(p) for p in driveway.polygon)
    return MapFeature(
        0,
        "driveway",
        (),
        polygon,
        {},
    )


_MAP_FEATURE_CONVERTERS = {
    "lane": _convert_lane,
    "road_line": _convert_road_line,
    "road_edge": _convert_road_edge,
    "crosswalk": _convert_crosswalk,
    "speed_bump": _convert_speed_bump,
    "stop_sign": _convert_stop_sign,
    "driveway": _convert_driveway,
}

_RULE_MAP_FEATURE_TYPES = frozenset({"lane", "stop_sign"})


class WaymoScenarioAdapter:
    def __init__(self, *, include_visual_map_features: bool = True) -> None:
        self.include_visual_map_features = include_visual_map_features

    def from_proto(self, scenario, source: str | None = None) -> ScenarioBundle:
        validate_scenario(scenario)

        timestamps = tuple(scenario.timestamps_seconds)
        current_time_index = scenario.current_time_index

        # Convert tracks to per-frame agent states
        tracks = list(scenario.tracks)
        num_steps = len(timestamps)
        frame_agents: list[list[AgentState]] = [[] for _ in range(num_steps)]

        for track_index, track in enumerate(tracks):
            track_id = track.id
            object_type = _normalize_object_type(track.object_type)
            for step_index, state in enumerate(track.states):
                agent = AgentState(
                    track_id,
                    track_index,
                    object_type,
                    timestamps[step_index],
                    Point3D(state.center_x, state.center_y, state.center_z),
                    state.velocity_x,
                    state.velocity_y,
                    state.heading,
                    state.length,
                    state.width,
                    state.height,
                    state.valid,
                )
                frame_agents[step_index].append(agent)

        # Convert dynamic map states to per-frame traffic lights
        frame_tls: list[list[TrafficLightState]] = [[] for _ in range(num_steps)]
        for step_index, dynamic_state in enumerate(scenario.dynamic_map_states):
            for lane_state in dynamic_state.lane_states:
                stop_point = None
                if lane_state.HasField("stop_point"):
                    stop_point = _to_point3d(lane_state.stop_point)
                tl = TrafficLightState(
                    lane_state.lane,
                    _normalize_lane_state(lane_state.state),
                    stop_point,
                )
                frame_tls[step_index].append(tl)

        # Build frames
        frames = []
        for step_index in range(num_steps):
            if step_index < current_time_index:
                phase = "history"
            elif step_index == current_time_index:
                phase = "current"
            else:
                phase = "future"
            frame = Frame(
                scenario.scenario_id,
                step_index,
                timestamps[step_index],
                phase,
                tuple(frame_agents[step_index]),
                tuple(frame_tls[step_index]),
            )
            frames.append(frame)

        # Convert map features
        map_features: dict[int, MapFeature] = {}
        for feat in scenario.map_features:
            feature_type = feat.WhichOneof("feature_data")
            if (
                not self.include_visual_map_features
                and feature_type not in _RULE_MAP_FEATURE_TYPES
            ):
                continue
            converter = _MAP_FEATURE_CONVERTERS.get(feature_type)
            if converter is None:
                continue
            mf = converter(getattr(feat, feature_type))
            mf = MapFeature(
                feat.id,
                mf.feature_type,
                mf.polyline,
                mf.polygon,
                mf.properties,
            )
            map_features[feat.id] = mf

        # Convert prediction targets
        prediction_targets = []
        for ttp in scenario.tracks_to_predict:
            track = tracks[ttp.track_index]
            pt = PredictionTarget(
                ttp.track_index,
                track.id,
                _normalize_difficulty(ttp.difficulty),
                _normalize_object_type(track.object_type),
            )
            prediction_targets.append(pt)

        has_lidar_data = len(scenario.compressed_frame_laser_data) > 0

        return ScenarioBundle(
            scenario.scenario_id,
            timestamps,
            current_time_index,
            scenario.sdc_track_index,
            tuple(scenario.objects_of_interest),
            tuple(prediction_targets),
            tuple(frames),
            map_features,
            source,
            has_lidar_data,
        )
