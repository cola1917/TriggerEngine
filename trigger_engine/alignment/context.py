from dataclasses import dataclass, field

from trigger_engine.data.frames import Frame, MapFeature


@dataclass(frozen=True)
class Watermark:
    scenario_id: str
    step_index: int
    timestamp_seconds: float


@dataclass(frozen=True)
class AlignedFrame:
    frame: Frame
    visibility: str
    available_modalities: frozenset[str]


@dataclass(frozen=True)
class AlignmentContext:
    scenario_id: str
    watermark: Watermark
    observed_frames: tuple[AlignedFrame, ...]
    current_frame: AlignedFrame
    future_frames: tuple[AlignedFrame, ...]
    input_frames: tuple[AlignedFrame, ...]
    source: str | None = None
    map_features: dict[int, MapFeature] = field(default_factory=dict)
    sdc_track_index: int | None = None
    sdc_track_id: int | None = None
    lane_match_cache: dict[tuple, object] = field(default_factory=dict, compare=False, hash=False)
    lane_match_index_cache: dict[tuple, object] = field(default_factory=dict, compare=False, hash=False)
    red_light_lane_cache: dict[tuple, object] = field(default_factory=dict, compare=False, hash=False)
    lane_heading_change_cache: dict[tuple, object] = field(default_factory=dict, compare=False, hash=False)
