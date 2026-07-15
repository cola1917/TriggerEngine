from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class AgentState:
    track_id: int | str
    track_index: int
    object_type: str
    timestamp_seconds: float
    center: Point3D
    velocity_x: float
    velocity_y: float
    heading: float
    length: float
    width: float
    height: float
    valid: bool


@dataclass(frozen=True)
class TrafficLightState:
    lane_id: int
    state: str
    stop_point: Point3D | None


@dataclass(frozen=True)
class MapFeature:
    feature_id: int
    feature_type: str
    polyline: tuple[Point3D, ...]
    polygon: tuple[Point3D, ...]
    properties: dict[str, object]


@dataclass(frozen=True)
class PredictionTarget:
    track_index: int
    track_id: int | str
    difficulty: str
    object_type: str


@dataclass(frozen=True)
class FrameSampling:
    source_hz: float | None = None
    target_hz: float | None = None
    resampled: bool = False
    interpolation: str | None = None


@dataclass(frozen=True)
class DataSourceMetadata:
    source_type: str
    dataset_version: str | None = None
    scene_name: str | None = None
    scene_token: str | None = None
    sample_count: int | None = None
    map_location: str | None = None
    log_token: str | None = None
    origin_global_translation: tuple[float, float, float] | None = None
    origin_global_rotation_wxyz: tuple[float, float, float, float] | None = None
    origin_global_yaw_rad: float | None = None
    coordinate_frame: str = "unknown"
    native_track_id_type: str = "unknown"
    frame_sampling: FrameSampling = field(default_factory=FrameSampling)
    skipped_rule_reasons: dict[str, str] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrajectoryQualityIssue:
    issue_type: str
    track_id: int | str
    frame_index: int
    timestamp_seconds: float
    value: float
    threshold: float
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Frame:
    scenario_id: str
    step_index: int
    timestamp_seconds: float
    phase: str
    agent_states: tuple[AgentState, ...]
    traffic_lights: tuple[TrafficLightState, ...]


@dataclass(frozen=True)
class ScenarioBundle:
    scenario_id: str
    timestamps_seconds: tuple[float, ...]
    current_time_index: int
    sdc_track_index: int
    objects_of_interest: tuple[int, ...]
    prediction_targets: tuple[PredictionTarget, ...]
    frames: tuple[Frame, ...]
    map_features: dict[int, MapFeature]
    source: str | None
    has_lidar_data: bool
    available_capabilities: frozenset[str] = field(default_factory=frozenset)
    metadata: DataSourceMetadata | None = None
    quality_issues: tuple[TrajectoryQualityIssue, ...] = ()
