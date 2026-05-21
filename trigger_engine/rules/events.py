from dataclasses import dataclass, field


@dataclass(frozen=True)
class TagEvent:
    scenario_id: str
    source: str | None
    frame_index: int
    timestamp_seconds: float
    tag_name: str
    subject_type: str
    subject_id: str | int | None
    value: bool | int | float | str
    rule_id: str
    metadata: dict[str, object] = field(default_factory=dict)
