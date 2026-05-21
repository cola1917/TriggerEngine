import argparse
import os
import struct
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
THIRD_PARTY = PROJECT_ROOT / "third_party"
DEFAULT_TFRECORD = PROJECT_ROOT / "data" / "validation_interactive.tfrecord-00000-of-00150"

if str(THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(THIRD_PARTY))


class TFRecordFormatError(ValueError):
    """Raised when a TFRecord file is incomplete or malformed."""


def _read_exact(file_obj, size, label):
    data = file_obj.read(size)
    if len(data) != size:
        raise TFRecordFormatError(f"Expected {size} bytes for {label}, got {len(data)}.")
    return data


def read_tfrecord(path):
    """Read the first record payload from a TFRecord file."""
    with open(path, "rb") as file_obj:
        length_bytes = _read_exact(file_obj, 8, "record length")
        length = struct.unpack("<Q", length_bytes)[0]
        _read_exact(file_obj, 4, "length crc")
        data = _read_exact(file_obj, length, "record payload")
        _read_exact(file_obj, 4, "data crc")
        return data


def load_scenario_pb2():
    try:
        from waymo_open_dataset.protos import scenario_pb2
    except ModuleNotFoundError as exc:
        if exc.name == "google":
            raise RuntimeError(
                "Missing dependency: google.protobuf. Install protobuf before parsing Waymo scenarios."
            ) from exc
        raise
    return scenario_pb2


def parse_scenario(record_data):
    scenario_pb2 = load_scenario_pb2()
    scenario = scenario_pb2.Scenario()
    try:
        scenario.ParseFromString(record_data)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to parse google.protobuf Scenario: {exc}"
        ) from exc
    return scenario


def scenario_from_tfrecord(path):
    return parse_scenario(read_tfrecord(path))


def object_type_name(object_type):
    return {
        0: "UNSET",
        1: "VEHICLE",
        2: "PEDESTRIAN",
        3: "CYCLIST",
        4: "OTHER",
    }.get(object_type, "?")


def lane_state_name(state):
    return {
        0: "UNKNOWN",
        1: "ARROW_STOP",
        2: "ARROW_CAUTION",
        3: "ARROW_GO",
        4: "STOP",
        5: "CAUTION",
        6: "GO",
        7: "FLASHING_STOP",
        8: "FLASHING_CAUTION",
    }.get(state, "?")


def difficulty_name(difficulty):
    return {0: "NONE", 1: "LEVEL_1", 2: "LEVEL_2"}.get(difficulty, "?")


def build_report(scenario):
    lines = []

    lines.append("=" * 60)
    lines.append(f"scenario_id: {scenario.scenario_id}")
    lines.append(f"timestamps_seconds: {len(scenario.timestamps_seconds)} steps")
    if scenario.timestamps_seconds:
        lines.append(
            f"  range: [{scenario.timestamps_seconds[0]:.2f}, {scenario.timestamps_seconds[-1]:.2f}]"
        )
    lines.append(f"current_time_index: {scenario.current_time_index}")
    lines.append(f"sdc_track_index: {scenario.sdc_track_index}")
    lines.append(f"objects_of_interest: {list(scenario.objects_of_interest)}")
    lines.append(f"tracks_to_predict: {len(scenario.tracks_to_predict)}")
    lines.append("")

    lines.append("=" * 60)
    lines.append(f"Tracks: {len(scenario.tracks)}")
    lines.append("=" * 60)
    for i, track in enumerate(scenario.tracks[:8]):
        valid_count = sum(1 for state in track.states if state.valid)
        lines.append(
            f"  [{i}] id={track.id}, type={object_type_name(track.object_type)}, "
            f"steps={len(track.states)}, valid={valid_count}"
        )
    if len(scenario.tracks) > 8:
        lines.append(f"  ... total {len(scenario.tracks)}")
    lines.append("")

    if scenario.tracks:
        track = scenario.tracks[0]
        lines.append("-" * 60)
        lines.append(f"Track[0] detail: id={track.id}, type={object_type_name(track.object_type)}")
        lines.append("-" * 60)
        if track.states:
            state = track.states[0]
            lines.append("  state[0]:")
            lines.append(f"    center_x={state.center_x:.4f}")
            lines.append(f"    center_y={state.center_y:.4f}")
            lines.append(f"    center_z={state.center_z:.4f}")
            lines.append(
                f"    length={state.length:.4f}, width={state.width:.4f}, height={state.height:.4f}"
            )
            lines.append(f"    heading={state.heading:.4f}")
            lines.append(f"    velocity_x={state.velocity_x:.4f}, velocity_y={state.velocity_y:.4f}")
            lines.append(f"    valid={state.valid}")
        lines.append("")

    lines.append("=" * 60)
    lines.append(f"Map Features: {len(scenario.map_features)}")
    lines.append("=" * 60)
    type_counts = {}
    for feature in scenario.map_features:
        feature_type = feature.WhichOneof("feature_data")
        type_counts[feature_type] = type_counts.get(feature_type, 0) + 1
    for feature_type, count in type_counts.items():
        lines.append(f"  {feature_type}: {count}")
    lines.append("")

    if scenario.map_features:
        feature = scenario.map_features[0]
        feature_type = feature.WhichOneof("feature_data")
        lines.append("-" * 60)
        lines.append(f"MapFeature[0]: id={feature.id}, type={feature_type}")
        lines.append("-" * 60)
        if feature_type == "lane":
            lane = feature.lane
            lines.append(f"  type={lane.type}, speed_limit={lane.speed_limit_mph} mph")
            lines.append(f"  polyline: {len(lane.polyline)} points")
            lines.append(f"  entry_lanes: {list(lane.entry_lanes)}")
            lines.append(f"  exit_lanes: {list(lane.exit_lanes)}")
            lines.append(f"  left_boundaries: {len(lane.left_boundaries)}")
            lines.append(f"  right_boundaries: {len(lane.right_boundaries)}")
            lines.append(f"  left_neighbors: {len(lane.left_neighbors)}")
            lines.append(f"  right_neighbors: {len(lane.right_neighbors)}")
        elif feature_type == "road_line":
            lines.append(f"  type={feature.road_line.type}")
            lines.append(f"  polyline: {len(feature.road_line.polyline)} points")
        elif feature_type == "road_edge":
            lines.append(f"  type={feature.road_edge.type}")
            lines.append(f"  polyline: {len(feature.road_edge.polyline)} points")
        elif feature_type == "crosswalk":
            lines.append(f"  polygon: {len(feature.crosswalk.polygon)} points")
        elif feature_type == "speed_bump":
            lines.append(f"  polygon: {len(feature.speed_bump.polygon)} points")
        elif feature_type == "stop_sign":
            stop_sign = feature.stop_sign
            lines.append(
                f"  position: ({stop_sign.position.x:.2f}, {stop_sign.position.y:.2f}, "
                f"{stop_sign.position.z:.2f})"
            )
            lines.append(f"  lanes: {list(stop_sign.lane)}")
        elif feature_type == "driveway":
            lines.append(f"  polygon: {len(feature.driveway.polygon)} points")
        lines.append("")

    lines.append("=" * 60)
    lines.append(f"Dynamic Map States: {len(scenario.dynamic_map_states)}")
    lines.append("=" * 60)
    if scenario.dynamic_map_states:
        dynamic_state = scenario.dynamic_map_states[scenario.current_time_index]
        lines.append(f"  at current_time_index: {len(dynamic_state.lane_states)} lane states")
        for i, lane_state in enumerate(dynamic_state.lane_states[:5]):
            lines.append(
                f"    [{i}] lane={lane_state.lane}, state={lane_state_name(lane_state.state)}"
            )
            if lane_state.HasField("stop_point"):
                lines.append(
                    f"        stop_point=({lane_state.stop_point.x:.2f}, {lane_state.stop_point.y:.2f})"
                )
        if len(dynamic_state.lane_states) > 5:
            lines.append(f"    ... total {len(dynamic_state.lane_states)}")
    lines.append("")

    lines.append("=" * 60)
    lines.append(f"Tracks to Predict: {len(scenario.tracks_to_predict)}")
    lines.append("=" * 60)
    for i, track_to_predict in enumerate(scenario.tracks_to_predict[:5]):
        track = scenario.tracks[track_to_predict.track_index]
        lines.append(
            f"  [{i}] track_index={track_to_predict.track_index}, "
            f"type={object_type_name(track.object_type)}, "
            f"difficulty={difficulty_name(track_to_predict.difficulty)}"
        )
    if len(scenario.tracks_to_predict) > 5:
        lines.append(f"  ... total {len(scenario.tracks_to_predict)}")

    return "\n".join(lines)


def inspect_frame(path=DEFAULT_TFRECORD):
    scenario = scenario_from_tfrecord(path)
    print(build_report(scenario))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect the first scenario in a Waymo TFRecord file.")
    parser.add_argument(
        "path",
        nargs="?",
        default=os.fspath(DEFAULT_TFRECORD),
        help="Path to a Waymo TFRecord shard.",
    )
    args = parser.parse_args(argv)
    try:
        inspect_frame(args.path)
    except (RuntimeError, TFRecordFormatError, FileNotFoundError) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
