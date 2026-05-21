from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class OperatorResult:
    operator_name: str
    subject_type: str
    subject_id: str | int | None
    frame_index: int
    timestamp_seconds: float
    value: bool | int | float | str
    metadata: dict[str, object] = field(default_factory=dict)


class Operator(Protocol):
    name: str
    result_kind: str
    subject_type: str

    def evaluate(
        self,
        context: object,
        frame: object,
        subject: object,
        args: Mapping[str, object],
    ) -> OperatorResult: ...
