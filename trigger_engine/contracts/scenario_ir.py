from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, sin
from pathlib import Path
import sys
from typing import Iterable

from trigger_engine.data.frames import AgentState, ScenarioBundle
from trigger_engine.rules.events import TagEvent


_CONTRACT_SRC = Path(__file__).resolve().parents[3] / "SceneExchangeContracts" / "src"
if str(_CONTRACT_SRC) not in sys.path:
    sys.path.insert(0, str(_CONTRACT_SRC))

from scene_exchange_contracts import validate_document


@dataclass(frozen=True)
class ScenarioIRExportConfig:
    """Controls how a mined bundle becomes a cross-project scenario contract."""

    scenario_type: str = "unknown"
    event_pre_seconds: float = 4.0
    event_post_seconds: float = 6.0
    reconstruction_pre_seconds: float = 12.0
    reconstruction_post_seconds: float = 12.0
    warmup_seconds: float = 2.0
    max_context_actors: int = 12


@dataclass(frozen=True)
class _IRTransform:
    origin_yaw_rad: float

    @classmethod
    def from_bundle(cls, bundle: ScenarioBundle) -> "_IRTransform":
        yaw = bundle.metadata.origin_global_yaw_rad if bundle.metadata else None
        return cls(origin_yaw_rad=float(yaw or 0.0))

    def xy(self, x: float, y: float) -> tuple[float, float]:
        cosine = cos(self.origin_yaw_rad)
        sine = sin(self.origin_yaw_rad)
        return cosine * x + sine * y, -sine * x + cosine * y

    def heading_deg(self, heading_rad: float) -> float:
        relative = heading_rad - self.origin_yaw_rad
        return degrees(atan2(sin(relative), cos(relative)))


def build_scenario_ir(
    bundle: ScenarioBundle,
    *,
    trigger_event: TagEvent | None = None,
    events: Iterable[TagEvent] = (),
    config: ScenarioIRExportConfig | None = None,
) -> dict[str, object]:
    config = config or ScenarioIRExportConfig()
    all_events = tuple(events)
    if trigger_event is None:
        trigger_event = _choose_trigger_event(all_events)

    trigger_time = (
        trigger_event.timestamp_seconds
        if trigger_event is not None
        else bundle.timestamps_seconds[bundle.current_time_index]
    )
    start_time = bundle.timestamps_seconds[0]
    end_time = bundle.timestamps_seconds[-1]
    event_window = _clamped_window(
        trigger_time - config.event_pre_seconds,
        trigger_time + config.event_post_seconds,
        start_time,
        end_time,
    )
    reconstruction_window = _clamped_window(
        event_window["start_sec"] - config.reconstruction_pre_seconds,
        event_window["end_sec"] + config.reconstruction_post_seconds,
        start_time,
        end_time,
    )
    warmup_window = _clamped_window(
        event_window["start_sec"] - config.warmup_seconds,
        event_window["start_sec"],
        start_time,
        event_window["start_sec"],
    )

    track_ids = _track_ids_for_window(bundle, reconstruction_window)
    trigger_actor_id = _trigger_actor_id(trigger_event)
    if trigger_actor_id is not None:
        track_ids = (trigger_actor_id,) + tuple(track_id for track_id in track_ids if track_id != trigger_actor_id)
    actor_ids = tuple(track_id for track_id in track_ids if track_id != "ego")[: config.max_context_actors]
    transform = _IRTransform.from_bundle(bundle)
    source_payload = _source_payload(bundle)
    ego_payload = _ego_payload(bundle, reconstruction_window, transform)
    actor_payloads = [
        _actor_payload(
            bundle,
            track_id,
            reconstruction_window,
            transform,
            role="trigger" if track_id == trigger_actor_id else "context",
        )
        for track_id in actor_ids
    ]

    scenario_id = _canonical_scene_id(bundle)
    scenario_ir = {
        "schema_version": "scenario_ir.v1",
        "scenario_id": scenario_id,
        "scenario_type": config.scenario_type,
        "source": source_payload,
        "coordinate_frame": _coordinate_frame_payload(bundle, transform),
        "windows": {
            "event": event_window,
            "warmup": warmup_window,
            "reconstruction": reconstruction_window,
        },
        "ego": ego_payload,
        "actors": actor_payloads,
        "map_context": _map_context_payload(bundle, transform),
        "sensors": _sensor_payload(bundle),
        "events": _events_payload(trigger_event, all_events),
        "data_requirements": _data_requirements_payload(),
        "risk_metrics": _risk_metrics_payload(trigger_event, ego_payload, actor_payloads, trigger_time),
        "dataset_refs": _dataset_refs_payload(source_payload),
        "evaluation": {
            "metrics": ["collision", "min_ttc", "route_progress", "comfort_jerk", "rule_violation"],
        },
        "variants": {
            "mvp": {
                "ego_speed_delta_mps": [-2.0, 0.0, 2.0],
                "actor_start_time_delta_sec": [-1.0, 0.0, 1.0],
                "weather": ["clear"],
            },
            "final_closed_loop": {
                "ego_policy": ["baseline", "ros2_stack"],
                "actor_policy": ["replay", "reactive_rule_based"],
                "sensor_domain": ["carla", "nurec", "cosmos_transfer1"],
            },
        },
    }
    validate_document(scenario_ir)
    return scenario_ir


def _source_payload(bundle: ScenarioBundle) -> dict[str, object]:
    metadata = bundle.metadata
    dataset = metadata.source_type if metadata else "unknown"
    scene_name = metadata.scene_name if metadata else None
    scene_token = metadata.scene_token if metadata else None
    if dataset == "nuscenes":
        scene_name = scene_name or bundle.scenario_id
        scene_token = scene_token or bundle.scenario_id
    payload: dict[str, object] = {
        "dataset": dataset,
        "scene_id": scene_token or bundle.scenario_id,
        "root": bundle.source,
    }
    optional = {
        "version": metadata.dataset_version if metadata else None,
        "scene_name": scene_name,
        "scene_token": scene_token,
        "sample_count": metadata.sample_count if metadata else None,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    return payload


def _canonical_scene_id(bundle: ScenarioBundle) -> str:
    if bundle.metadata and bundle.metadata.scene_token:
        return bundle.metadata.scene_token
    return bundle.scenario_id


def _coordinate_frame_payload(
    bundle: ScenarioBundle,
    transform: _IRTransform,
) -> dict[str, object]:
    metadata = bundle.metadata
    translation = (
        metadata.origin_global_translation
        if metadata and metadata.origin_global_translation is not None
        else (0.0, 0.0, 0.0)
    )
    rotation = (
        metadata.origin_global_rotation_wxyz
        if metadata and metadata.origin_global_rotation_wxyz is not None
        else (
            cos(transform.origin_yaw_rad / 2.0),
            0.0,
            0.0,
            sin(transform.origin_yaw_rad / 2.0),
        )
    )
    return {
        "name": "scene_local_ego_start",
        "units": {"position": "meter", "time": "second", "yaw": "degree"},
        "handedness": "right",
        "x_axis": "initial_ego_forward",
        "y_axis": "initial_ego_left",
        "origin_global_translation": [float(value) for value in translation],
        "origin_global_rotation_wxyz": [float(value) for value in rotation],
        "origin_global_yaw_deg": degrees(transform.origin_yaw_rad),
        "transform": "local_xy = R(-origin_yaw) * (global_xy - origin_xy)",
    }


def _data_requirements_payload() -> dict[str, object]:
    return {
        "reconstruction": {
            "required": [
                "camera_images",
                "camera_calibration",
                "ego_pose",
                "actor_tracks",
            ],
        },
        "closed_loop": {
            "required": [
                "ego_initial_state",
                "actor_initial_states",
                "map_context",
            ],
        },
    }


def _risk_metrics_payload(
    trigger_event: TagEvent | None,
    ego_payload: dict[str, object],
    actor_payloads: list[dict[str, object]],
    trigger_time: float,
) -> dict[str, object]:
    reference_trajectory = ego_payload.get("reference_trajectory", [])
    ego_reference_state_count = len(reference_trajectory) if isinstance(reference_trajectory, list) else 0
    return {
        "trigger_time_sec": round(trigger_time, 6),
        "trigger_tag": trigger_event.tag_name if trigger_event is not None else None,
        "actor_count": len(actor_payloads),
        "ego_reference_state_count": ego_reference_state_count,
    }


def _dataset_refs_payload(source_payload: dict[str, object]) -> dict[str, object]:
    source = {
        "dataset": source_payload["dataset"],
        "root": source_payload.get("root"),
        "scene_id": source_payload["scene_id"],
    }
    for name in ("version", "scene_name", "scene_token"):
        if name in source_payload:
            source[name] = source_payload[name]
    return {
        "source": source,
        "sample_refs": {"status": "deferred", "refs": []},
        "index_refs": {"status": "deferred", "refs": []},
    }


def _choose_trigger_event(events: tuple[TagEvent, ...]) -> TagEvent | None:
    review_events = [event for event in events if event.metadata.get("intent") == "review"]
    if review_events:
        return review_events[0]
    return events[0] if events else None


def _clamped_window(start: float, end: float, min_time: float, max_time: float) -> dict[str, float]:
    start = max(min_time, start)
    end = min(max_time, max(start, end))
    return {"start_sec": round(start, 6), "end_sec": round(end, 6)}


def _states_for_track(
    bundle: ScenarioBundle,
    track_id: str | int,
    window: dict[str, float],
) -> tuple[AgentState, ...]:
    states = []
    for frame in bundle.frames:
        if frame.timestamp_seconds < window["start_sec"] or frame.timestamp_seconds > window["end_sec"]:
            continue
        for agent in frame.agent_states:
            if agent.track_id == track_id and agent.valid:
                states.append(agent)
    return tuple(states)


def _track_ids_for_window(bundle: ScenarioBundle, window: dict[str, float]) -> tuple[str | int, ...]:
    seen = {}
    for frame in bundle.frames:
        if frame.timestamp_seconds < window["start_sec"] or frame.timestamp_seconds > window["end_sec"]:
            continue
        for agent in frame.agent_states:
            if agent.valid and agent.track_id not in seen:
                seen[agent.track_id] = len(seen)
    return tuple(seen)


def _ego_payload(
    bundle: ScenarioBundle,
    window: dict[str, float],
    transform: _IRTransform,
) -> dict[str, object]:
    states = _states_for_track(bundle, "ego", window)
    initial = states[0] if states else None
    return {
        "track_id": "ego",
        "initial_state": _state_payload(initial, transform) if initial else None,
        "reference_trajectory": [_state_payload(state, transform) for state in states],
        "route": {
            "source": "reference_trajectory",
            "note": "MVP route is inferred from ego reference states.",
        },
    }


def _actor_payload(
    bundle: ScenarioBundle,
    track_id: str | int,
    window: dict[str, float],
    transform: _IRTransform,
    *,
    role: str,
) -> dict[str, object]:
    states = _states_for_track(bundle, track_id, window)
    initial = states[0] if states else None
    return {
        "actor_id": str(track_id),
        "source_track_id": track_id,
        "role": role,
        "type": initial.object_type if initial else "unknown",
        "dimensions": _dimensions_payload(initial) if initial else None,
        "initial_state": _state_payload(initial, transform) if initial else None,
        "reference_trajectory": [_state_payload(state, transform) for state in states],
        "policy_hints": {
            "mvp": "replay",
            "final_closed_loop": "reference_conditioned_reactive_rule_based",
        },
    }


def _state_payload(
    state: AgentState | None,
    transform: _IRTransform,
) -> dict[str, float] | None:
    if state is None:
        return None
    x, y = transform.xy(state.center.x, state.center.y)
    vx, vy = transform.xy(state.velocity_x, state.velocity_y)
    return {
        "t_sec": round(state.timestamp_seconds, 6),
        "x": round(x, 6),
        "y": round(y, 6),
        "z": round(state.center.z, 6),
        "yaw": round(transform.heading_deg(state.heading), 6),
        "vx": round(vx, 6),
        "vy": round(vy, 6),
        "speed_mps": round(hypot(vx, vy), 6),
    }


def _dimensions_payload(state: AgentState | None) -> dict[str, float] | None:
    if state is None:
        return None
    return {
        "length": round(state.length, 6),
        "width": round(state.width, 6),
        "height": round(state.height, 6),
    }


def _map_context_payload(
    bundle: ScenarioBundle,
    transform: _IRTransform,
) -> dict[str, object]:
    map_features = bundle.map_features
    counts: dict[str, int] = {}
    for feature in map_features.values():
        counts[feature.feature_type] = counts.get(feature.feature_type, 0) + 1
    return {
        "location": bundle.metadata.map_location if bundle.metadata else None,
        "log_token": bundle.metadata.log_token if bundle.metadata else None,
        "feature_counts": dict(sorted(counts.items())),
        "features": [
            {
                "id": feature.feature_id,
                "type": feature.feature_type,
                "polyline": [_point_payload(point, transform) for point in feature.polyline],
                "polygon": [_point_payload(point, transform) for point in feature.polygon],
                "properties": feature.properties,
            }
            for feature in map_features.values()
        ],
    }


def _sensor_payload(bundle: ScenarioBundle) -> dict[str, object]:
    return {
        "available_capabilities": sorted(bundle.available_capabilities),
        "camera_calibration": "deferred_to_dataset_adapter",
        "notes": [
            "MVP Scenario IR declares required sensor capability but does not inline image paths or calibration tables.",
            "NeuralSceneBridge resolves nuScenes image/calibration records from source.root and source.scene_id.",
        ],
    }


def _events_payload(trigger_event: TagEvent | None, events: tuple[TagEvent, ...]) -> dict[str, object]:
    return {
        "trigger": _event_payload(trigger_event) if trigger_event is not None else None,
        "mined_events": [_event_payload(event) for event in events],
    }


def _event_payload(event: TagEvent | None) -> dict[str, object] | None:
    if event is None:
        return None
    return {
        "tag_name": event.tag_name,
        "rule_id": event.rule_id,
        "frame_index": event.frame_index,
        "timestamp_seconds": round(event.timestamp_seconds, 6),
        "subject_type": event.subject_type,
        "subject_id": event.subject_id,
        "metadata": event.metadata,
    }


def _trigger_actor_id(event: TagEvent | None) -> str | int | None:
    if event is None:
        return None
    if event.metadata.get("target_id") is not None:
        return event.metadata["target_id"]
    if event.subject_type in ("agent", "sdc_agent") and event.subject_id != "ego":
        return event.subject_id
    if isinstance(event.subject_id, str) and ":" in event.subject_id:
        return event.subject_id.split(":", 1)[-1]
    return None


def _point_payload(point, transform: _IRTransform) -> dict[str, float]:
    x, y = transform.xy(point.x, point.y)
    return {"x": round(x, 6), "y": round(y, 6), "z": round(point.z, 6)}
