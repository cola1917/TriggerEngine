from dataclasses import dataclass, field


@dataclass(frozen=True)
class OperatorCall:
    operator_name: str
    args: dict[str, object] = field(default_factory=dict)
    for_last_n_frames: int | None = None


@dataclass(frozen=True)
class AllCondition:
    calls: tuple[OperatorCall, ...]


@dataclass(frozen=True)
class SustainedTagCondition:
    tag_name: str
    frames: int | None = None
    seconds: float | None = None


@dataclass(frozen=True)
class SequenceStep:
    tag_name: str


@dataclass(frozen=True)
class SequenceTagCondition:
    steps: tuple[SequenceStep, ...]
    within_frames: int | None = None
    within_seconds: float | None = None
    max_gap_frames: int | None = None


@dataclass(frozen=True)
class EventCompactionPolicy:
    by: str = "subject"
    mode: str = "interval"


@dataclass(frozen=True)
class ReviewEpisodePolicy:
    by: str = "subject"
    mode: str = "interval"


@dataclass(frozen=True)
class EventPolicy:
    cooldown_frames: int = 0
    compact: EventCompactionPolicy | None = None
    episode: ReviewEpisodePolicy | None = None


_VALID_INTENTS = frozenset({"review", "supporting", "debug"})


@dataclass(frozen=True)
class RuleEmit:
    tag_name: str
    value: bool | int | float | str = True
    metadata: dict[str, object] = field(default_factory=dict)
    policy: EventPolicy = field(default_factory=EventPolicy)
    intent: str = "debug"


@dataclass(frozen=True)
class PairConfig:
    mode: str = "directed"


@dataclass(frozen=True)
class RuleWindow:
    history_steps: int | None = None


@dataclass(frozen=True)
class Rule:
    rule_id: str
    subject_type: str
    condition: AllCondition | SustainedTagCondition | SequenceTagCondition
    emit: RuleEmit
    kind: str = "single_frame"
    description: str | None = None
    window: RuleWindow | None = None
    pair: PairConfig = field(default_factory=PairConfig)


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
