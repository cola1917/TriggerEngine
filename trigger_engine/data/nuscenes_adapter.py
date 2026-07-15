from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .frames import (
    AgentState,
    DataSourceMetadata,
    Frame,
    FrameSampling,
    MapFeature,
    Point3D,
    ScenarioBundle,
)
from .validation import DataAdapterError


_EGO_TRACK_ID = "ego"


class NuScenesAdapter:
    source_type = "nuscenes"

    def load(
        self,
        source: str | Path,
        *,
        version: str = "v1.0-mini",
        scene: str | None = None,
        current_time_index: int | None = None,
    ) -> ScenarioBundle:
        dataroot = Path(source)
        tables = _NuScenesTables.load(dataroot / version, maps_root=dataroot / "maps")
        scene_record = tables.scene_by_name_or_token(scene) if scene else tables.scenes[0]
        return self.from_tables(
            tables,
            scene_record=scene_record,
            source=str(dataroot),
            dataset_version=version,
            current_time_index=current_time_index,
        )

    @classmethod
    def from_devkit(
        cls,
        nusc,
        *,
        scene: str | None = None,
        current_time_index: int | None = None,
    ) -> ScenarioBundle:
        tables = _NuScenesTables.from_devkit(nusc)
        scene_record = tables.scene_by_name_or_token(scene) if scene else tables.scenes[0]
        dataroot = getattr(nusc, "dataroot", None)
        return cls().from_tables(
            tables,
            scene_record=scene_record,
            source=str(dataroot) if dataroot is not None else None,
            dataset_version=getattr(nusc, "version", None),
            current_time_index=current_time_index,
        )

    def from_tables(
        self,
        tables: "_NuScenesTables",
        *,
        scene_record: dict,
        source: str | None = None,
        dataset_version: str | None = None,
        current_time_index: int | None = None,
    ) -> ScenarioBundle:
        samples = tables.samples_for_scene(scene_record)
        if not samples:
            raise DataAdapterError("nuScenes scene has no samples")

        timestamps = _relative_timestamps(samples)
        if current_time_index is None:
            current_time_index = len(samples) - 1
        if current_time_index < 0 or current_time_index >= len(samples):
            raise DataAdapterError(
                f"current_time_index={current_time_index} out of range [0, {len(samples)})"
            )

        annotations_by_sample = tables.annotations_by_sample()
        object_type_by_instance = tables.object_type_by_instance()
        track_indices = _track_indices(samples, annotations_by_sample)
        origin = _ego_origin(tables, samples[0])
        origin_pose = tables.ego_pose_for_sample(samples[0])
        origin_rotation = (
            tuple(float(value) for value in origin_pose["rotation"])
            if origin_pose is not None
            else (1.0, 0.0, 0.0, 0.0)
        )
        origin_yaw = _yaw_from_quaternion(list(origin_rotation))
        map_features = _map_features_for_scene(tables, scene_record, origin)
        velocities = _annotation_velocities(samples, annotations_by_sample)
        ego_velocities = _ego_velocities(tables, samples)

        frames: list[Frame] = []
        for step_index, sample in enumerate(samples):
            phase = _phase(step_index, current_time_index)
            sample_token = sample["token"]
            agents: list[AgentState] = []
            ego_pose = tables.ego_pose_for_sample(sample)
            if ego_pose is not None:
                ego_position = _local_point(ego_pose["translation"], origin)
                evx, evy = ego_velocities.get(step_index, (0.0, 0.0))
                agents.append(
                    AgentState(
                        track_id=_EGO_TRACK_ID,
                        track_index=0,
                        object_type="vehicle",
                        timestamp_seconds=timestamps[step_index],
                        center=ego_position,
                        velocity_x=evx,
                        velocity_y=evy,
                        heading=_yaw_from_quaternion(ego_pose["rotation"]),
                        length=4.8,
                        width=1.9,
                        height=1.7,
                        valid=True,
                    )
                )

            for ann in annotations_by_sample.get(sample_token, ()):
                instance_token = ann["instance_token"]
                vx, vy = velocities.get((sample_token, instance_token), (0.0, 0.0))
                width, length, height = ann["size"]
                agents.append(
                    AgentState(
                        track_id=instance_token,
                        track_index=track_indices[instance_token],
                        object_type=object_type_by_instance.get(instance_token, "other"),
                        timestamp_seconds=timestamps[step_index],
                        center=_local_point(ann["translation"], origin),
                        velocity_x=vx,
                        velocity_y=vy,
                        heading=_yaw_from_quaternion(ann["rotation"]),
                        length=length,
                        width=width,
                        height=height,
                        valid=True,
                    )
                )

            frames.append(
                Frame(
                    scenario_id=scene_record["token"],
                    step_index=step_index,
                    timestamp_seconds=timestamps[step_index],
                    phase=phase,
                    agent_states=tuple(agents),
                    traffic_lights=(),
                )
            )

        has_lidar_data = tables.has_modality("lidar")
        log_record = tables.log_for_scene(scene_record) or {}
        metadata = DataSourceMetadata(
            source_type=self.source_type,
            dataset_version=dataset_version,
            scene_name=str(scene_record["name"]),
            scene_token=str(scene_record["token"]),
            sample_count=len(samples),
            map_location=log_record.get("location"),
            log_token=str(scene_record.get("log_token") or "") or None,
            origin_global_translation=tuple(float(value) for value in origin),
            origin_global_rotation_wxyz=origin_rotation,
            origin_global_yaw_rad=origin_yaw,
            coordinate_frame="scene_local_global_axes",
            native_track_id_type="str",
            frame_sampling=FrameSampling(
                source_hz=_estimate_hz(timestamps),
                target_hz=None,
                resampled=False,
                interpolation=None,
            ),
            skipped_rule_reasons={
                "traffic_lights": "nuScenes mini does not provide per-frame traffic-light state."
            },
            notes=(
                "Agent states are nuScenes keyframe annotations; no dense interpolation is applied.",
                "Ego pose is exposed as track_id='ego' for SDC-compatible rules.",
                "Internal positions subtract the first ego translation but retain nuScenes global XY axes and radian headings.",
                "Scenario IR export rotates this internal frame into the first-ego-forward frame.",
            ),
        )

        return ScenarioBundle(
            scenario_id=scene_record["token"],
            timestamps_seconds=timestamps,
            current_time_index=current_time_index,
            sdc_track_index=0,
            objects_of_interest=(),
            prediction_targets=(),
            frames=tuple(frames),
            map_features=map_features,
            source=source,
            has_lidar_data=has_lidar_data,
            available_capabilities=_sensor_capabilities(tables) | (frozenset({"map"}) if map_features else frozenset()),
            metadata=metadata,
        )


class _NuScenesTables:
    def __init__(self, tables: dict[str, list[dict]], maps_root: Path | None = None) -> None:
        self.tables = tables
        self.scenes = tables["scene"]
        self.maps_root = maps_root
        self._sample_by_token = {row["token"]: row for row in tables["sample"]}
        self._log_by_token = {row["token"]: row for row in tables.get("log", [])}
        self._ego_pose_by_token = {row["token"]: row for row in tables.get("ego_pose", [])}
        self._sample_data_by_sample = _group_by(tables.get("sample_data", []), "sample_token")
        self._sensor_by_token = {row["token"]: row for row in tables.get("sensor", [])}
        self._calibrated_sensor_by_token = {
            row["token"]: row for row in tables.get("calibrated_sensor", [])
        }

    @classmethod
    def load(cls, table_dir: Path, maps_root: Path | None = None) -> "_NuScenesTables":
        if not table_dir.exists():
            raise DataAdapterError(f"nuScenes table directory does not exist: {table_dir}")
        required = ("scene", "sample", "sample_annotation", "instance", "category")
        tables = {name: _read_json_table(table_dir / f"{name}.json") for name in required}
        for optional in ("ego_pose", "sample_data", "sensor", "calibrated_sensor", "log", "map"):
            path = table_dir / f"{optional}.json"
            tables[optional] = _read_json_table(path) if path.exists() else []
        return cls(tables, maps_root=maps_root)

    @classmethod
    def from_devkit(cls, nusc) -> "_NuScenesTables":
        names = (
            "scene",
            "sample",
            "sample_annotation",
            "instance",
            "category",
            "ego_pose",
            "sample_data",
            "sensor",
            "calibrated_sensor",
            "log",
            "map",
        )
        dataroot = getattr(nusc, "dataroot", None)
        maps_root = Path(dataroot) / "maps" if dataroot is not None else None
        return cls({name: list(getattr(nusc, name, [])) for name in names}, maps_root=maps_root)

    def scene_by_name_or_token(self, value: str) -> dict:
        for scene in self.scenes:
            if scene["name"] == value or scene["token"] == value:
                return scene
        raise DataAdapterError(f"nuScenes scene not found: {value}")

    def samples_for_scene(self, scene: dict) -> list[dict]:
        samples = []
        token = scene["first_sample_token"]
        while token:
            sample = self._sample_by_token[token]
            samples.append(sample)
            if token == scene.get("last_sample_token"):
                break
            token = sample.get("next", "")
        return samples

    def annotations_by_sample(self) -> dict[str, tuple[dict, ...]]:
        grouped = _group_by(self.tables["sample_annotation"], "sample_token")
        return {key: tuple(value) for key, value in grouped.items()}

    def object_type_by_instance(self) -> dict[str, str]:
        categories = {row["token"]: row["name"] for row in self.tables["category"]}
        result = {}
        for instance in self.tables["instance"]:
            name = categories.get(instance["category_token"], "")
            result[instance["token"]] = _normalize_category(name)
        return result

    def ego_pose_for_sample(self, sample: dict) -> dict | None:
        for sample_data in self._sample_data_by_sample.get(sample["token"], ()):
            sensor = self._sensor_for_sample_data(sample_data)
            if sensor is not None and sensor.get("channel") == "LIDAR_TOP":
                return self._ego_pose_by_token.get(sample_data["ego_pose_token"])
        for sample_data in self._sample_data_by_sample.get(sample["token"], ()):
            if sample_data.get("is_key_frame"):
                return self._ego_pose_by_token.get(sample_data["ego_pose_token"])
        return None

    def has_modality(self, modality: str) -> bool:
        return any(row.get("modality") == modality for row in self._sensor_by_token.values())

    def modalities(self) -> frozenset[str]:
        return frozenset(row.get("modality") for row in self._sensor_by_token.values())

    def map_json_for_scene(self, scene: dict) -> dict | None:
        if self.maps_root is None:
            return None
        log = self.log_for_scene(scene)
        if log is None:
            return None
        location = log.get("location")
        if not location:
            return None
        map_path = self.maps_root / f"{location}.json"
        if not map_path.exists():
            return None
        return json.loads(map_path.read_text(encoding="utf-8"))

    def log_for_scene(self, scene: dict) -> dict | None:
        return self._log_by_token.get(scene.get("log_token", ""))

    def _sensor_for_sample_data(self, sample_data: dict) -> dict | None:
        calibrated = self._calibrated_sensor_by_token.get(sample_data["calibrated_sensor_token"])
        if calibrated is None:
            return None
        return self._sensor_by_token.get(calibrated["sensor_token"])


def _read_json_table(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _group_by(rows: Iterable[dict], key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row[key]].append(row)
    return grouped


def _relative_timestamps(samples: list[dict]) -> tuple[float, ...]:
    first = samples[0]["timestamp"]
    return tuple((sample["timestamp"] - first) / 1_000_000.0 for sample in samples)


def _track_indices(samples: list[dict], annotations_by_sample: dict[str, tuple[dict, ...]]) -> dict[str, int]:
    indices: dict[str, int] = {}
    next_index = 1
    for sample in samples:
        for ann in annotations_by_sample.get(sample["token"], ()):
            token = ann["instance_token"]
            if token not in indices:
                indices[token] = next_index
                next_index += 1
    return indices


def _ego_origin(tables: _NuScenesTables, sample: dict) -> tuple[float, float, float]:
    ego_pose = tables.ego_pose_for_sample(sample)
    if ego_pose is None:
        return (0.0, 0.0, 0.0)
    x, y, z = ego_pose["translation"]
    return (x, y, z)


def _map_features_for_scene(
    tables: _NuScenesTables,
    scene: dict,
    origin: tuple[float, float, float],
) -> dict[int, MapFeature]:
    map_json = tables.map_json_for_scene(scene)
    if not map_json:
        return {}

    nodes = {row["token"]: row for row in map_json.get("node", [])}
    polygons = {row["token"]: row for row in map_json.get("polygon", [])}
    lines = {row["token"]: row for row in map_json.get("line", [])}
    features: dict[int, MapFeature] = {}
    next_id = 1

    def node_point(token: str) -> Point3D | None:
        node = nodes.get(token)
        if node is None:
            return None
        return Point3D(node["x"] - origin[0], node["y"] - origin[1], 0.0)

    def polygon_points(token: str) -> tuple[Point3D, ...]:
        polygon = polygons.get(token)
        if polygon is None:
            return ()
        points = [node_point(node_token) for node_token in polygon.get("exterior_node_tokens", [])]
        return tuple(point for point in points if point is not None)

    def line_points(token: str) -> tuple[Point3D, ...]:
        line = lines.get(token)
        if line is None:
            return ()
        points = [node_point(node_token) for node_token in line.get("node_tokens", [])]
        return tuple(point for point in points if point is not None)

    def add_polygon(feature_type: str, row: dict, polygon_token: str, properties: dict[str, object] | None = None) -> None:
        nonlocal next_id
        points = polygon_points(polygon_token)
        if len(points) < 3:
            return
        features[next_id] = MapFeature(
            feature_id=next_id,
            feature_type=feature_type,
            polyline=(),
            polygon=points,
            properties={
                "token": row.get("token", ""),
                **(properties or {}),
            },
        )
        next_id += 1

    def add_line(feature_type: str, row: dict, line_token: str, properties: dict[str, object] | None = None) -> None:
        nonlocal next_id
        points = line_points(line_token)
        if len(points) < 2:
            return
        features[next_id] = MapFeature(
            feature_id=next_id,
            feature_type=feature_type,
            polyline=points,
            polygon=(),
            properties={
                "token": row.get("token", ""),
                **(properties or {}),
            },
        )
        next_id += 1

    for row in map_json.get("lane", []):
        add_polygon("lane", row, row.get("polygon_token", ""), {"lane_type": row.get("lane_type", "")})
    for row in map_json.get("road_segment", []):
        add_polygon("road_segment", row, row.get("polygon_token", ""), {"is_intersection": row.get("is_intersection", False)})
    for row in map_json.get("walkway", []):
        add_polygon("walkway", row, row.get("polygon_token", ""))
    for row in map_json.get("ped_crossing", []):
        add_polygon("ped_crossing", row, row.get("polygon_token", ""))
    for row in map_json.get("stop_line", []):
        add_polygon("stop_line", row, row.get("polygon_token", ""), {"stop_line_type": row.get("stop_line_type", "")})
    for row in map_json.get("road_divider", []):
        add_line("road_divider", row, row.get("line_token", ""))
    for row in map_json.get("lane_divider", []):
        add_line("lane_divider", row, row.get("line_token", ""))
    for row in map_json.get("drivable_area", []):
        for polygon_token in row.get("polygon_tokens", []):
            add_polygon("drivable_area", row, polygon_token)

    return features


def _local_point(translation: list[float], origin: tuple[float, float, float]) -> Point3D:
    return Point3D(
        x=translation[0] - origin[0],
        y=translation[1] - origin[1],
        z=translation[2] - origin[2],
    )


def _yaw_from_quaternion(rotation: list[float]) -> float:
    w, x, y, z = rotation
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _phase(step_index: int, current_time_index: int) -> str:
    if step_index < current_time_index:
        return "history"
    if step_index == current_time_index:
        return "current"
    return "future"


def _annotation_velocities(
    samples: list[dict],
    annotations_by_sample: dict[str, tuple[dict, ...]],
) -> dict[tuple[str, str], tuple[float, float]]:
    by_instance: dict[str, list[tuple[str, float, list[float]]]] = defaultdict(list)
    first_timestamp = samples[0]["timestamp"]
    for sample in samples:
        ts = (sample["timestamp"] - first_timestamp) / 1_000_000.0
        for ann in annotations_by_sample.get(sample["token"], ()):
            by_instance[ann["instance_token"]].append((sample["token"], ts, ann["translation"]))

    velocities: dict[tuple[str, str], tuple[float, float]] = {}
    for instance_token, points in by_instance.items():
        for index, (sample_token, ts, translation) in enumerate(points):
            if len(points) == 1:
                velocity = (0.0, 0.0)
            elif index == 0:
                _, next_ts, next_translation = points[index + 1]
                velocity = _velocity(translation, next_translation, next_ts - ts)
            elif index == len(points) - 1:
                _, prev_ts, prev_translation = points[index - 1]
                velocity = _velocity(prev_translation, translation, ts - prev_ts)
            else:
                _, prev_ts, prev_translation = points[index - 1]
                _, next_ts, next_translation = points[index + 1]
                velocity = _velocity(prev_translation, next_translation, next_ts - prev_ts)
            velocities[(sample_token, instance_token)] = velocity
    return velocities


def _ego_velocities(tables: _NuScenesTables, samples: list[dict]) -> dict[int, tuple[float, float]]:
    poses = [tables.ego_pose_for_sample(sample) for sample in samples]
    timestamps = _relative_timestamps(samples)
    velocities = {}
    for index, pose in enumerate(poses):
        if pose is None:
            velocities[index] = (0.0, 0.0)
            continue
        if len(poses) == 1:
            velocities[index] = (0.0, 0.0)
        elif index == 0 and poses[index + 1] is not None:
            velocities[index] = _velocity(
                pose["translation"], poses[index + 1]["translation"], timestamps[index + 1] - timestamps[index]
            )
        elif index == len(poses) - 1 and poses[index - 1] is not None:
            velocities[index] = _velocity(
                poses[index - 1]["translation"], pose["translation"], timestamps[index] - timestamps[index - 1]
            )
        elif poses[index - 1] is not None and poses[index + 1] is not None:
            velocities[index] = _velocity(
                poses[index - 1]["translation"],
                poses[index + 1]["translation"],
                timestamps[index + 1] - timestamps[index - 1],
            )
        else:
            velocities[index] = (0.0, 0.0)
    return velocities


def _velocity(start: list[float], end: list[float], dt: float) -> tuple[float, float]:
    if dt <= 0.0:
        return (0.0, 0.0)
    return ((end[0] - start[0]) / dt, (end[1] - start[1]) / dt)


def _normalize_category(name: str) -> str:
    if name.startswith("vehicle.bicycle"):
        return "cyclist"
    if name.startswith("vehicle.motorcycle"):
        return "cyclist"
    if name.startswith("vehicle."):
        return "vehicle"
    if name.startswith("human.pedestrian"):
        return "pedestrian"
    return "other"


def _estimate_hz(timestamps: tuple[float, ...]) -> float | None:
    if len(timestamps) < 2:
        return None
    intervals = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
    if not intervals:
        return None
    return 1.0 / (sum(intervals) / len(intervals))


def _sensor_capabilities(tables: _NuScenesTables) -> frozenset[str]:
    return frozenset(modality for modality in tables.modalities() if modality)
