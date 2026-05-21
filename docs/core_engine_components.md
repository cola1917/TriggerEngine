# Core Engine 组件设计

## 包结构

建议新增：

```text
trigger_engine/
  engine/
    __init__.py
    compiler.py
    registry.py
    timeline.py
    trigger_engine.py
```

现有包继续保留：

```text
trigger_engine/operators/
trigger_engine/rules/
trigger_engine/alignment/
```

## Rule AST 扩展

### Rule.kind

`Rule` 增加：

```python
kind: str = "single_frame"
```

取值：

- `"single_frame"`
- `"temporal"`

### TemporalCondition

```python
@dataclass(frozen=True)
class SustainedTagCondition:
    tag_name: str
    frames: int
```

语义：

- 对同一 `subject_type + subject_id`
- 在当前 frame 结束的最近 N 个 input frame 中
- 每一帧都存在指定 `tag_name`

### Rule.condition

第一阶段允许：

```python
AllCondition               # single_frame
SustainedTagCondition      # temporal
```

## ExecutionPlan

```python
@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    single_frame_rules: tuple[Rule, ...]
    temporal_rules: tuple[Rule, ...]
    operator_names: tuple[str, ...]
```

约束：

- `single_frame_rules` 只包含 `kind="single_frame"`
- `temporal_rules` 只包含 `kind="temporal"`
- `operator_names` 只来自 single-frame rules

## RuleCompiler

```python
class RuleCompiler:
    def compile(
        self,
        plan_id: str,
        rule_set: RuleSet,
        operator_registry: OperatorRegistry,
    ) -> ExecutionPlan:
        ...
```

校验：

- rule kind 必须合法
- single-frame rule 必须使用 `AllCondition`
- single-frame rule 中每个 operator 必须已注册
- operator `subject_type` 必须匹配 rule subject
- operator `result_kind` 必须是 `"predicate"`
- temporal rule 必须使用 `SustainedTagCondition`
- temporal rule 不允许包含 operator call
- temporal rule source tag 必须由同 plan 内某个 single-frame rule emit
- temporal rule subject 必须和 source tag 的 subject 一致
- `frames` 必须为正整数

错误统一抛 `RuleCompileError`。

## RuleRegistry

```python
class RuleRegistry:
    def register(self, plan: ExecutionPlan) -> None:
        ...

    def register_yaml(self, name: str, yaml_text: str) -> ExecutionPlan:
        ...

    def activate(self, plan_id: str) -> None:
        ...

    def active_plan(self) -> ExecutionPlan:
        ...
```

依赖：

- `RuleParser`
- `RuleCompiler`
- `OperatorRegistry`

行为：

- `register_yaml` 会 parse + compile + register
- operator 缺失时注册失败
- 没有 active plan 时 `active_plan()` 抛 `RuleRegistryError`
- 重复 plan id 默认拒绝，后续可增加 explicit update

## TagTimeline

```python
@dataclass(frozen=True)
class TagKey:
    tag_name: str
    subject_type: str
    subject_id: str | int | None
```

```python
class TagTimeline:
    @classmethod
    def from_events(cls, events: Iterable[TagEvent]) -> TagTimeline:
        ...

    def has_at(self, key: TagKey, frame_index: int) -> bool:
        ...

    def sustained(
        self,
        key: TagKey,
        end_frame_index: int,
        frames: int,
    ) -> tuple[bool, tuple[int, ...]]:
        ...
```

`sustained` 返回：

- 是否满足
- 支撑该判断的 frame indices

## TriggerEngine

```python
class TriggerEngine:
    def __init__(
        self,
        operator_registry: OperatorRegistry,
        rule_registry: RuleRegistry,
        rule_engine: RuleEngine | None = None,
    ):
        ...

    def evaluate(self, context: AlignmentContext) -> EngineResult:
        ...
```

注意：

- 没有 `rule_yaml` 入参
- 没有 `ScenarioBundle` 入参
- 只消费 `AlignmentContext`

执行：

1. `plan = rule_registry.active_plan()`
2. `single_events = rule_engine.evaluate(RuleSet(plan.single_frame_rules), context)`
3. `timeline = TagTimeline.from_events(single_events)`
4. `temporal_events = temporal_engine.evaluate(plan.temporal_rules, context, timeline)`
5. 返回 `EngineResult`

## TemporalRuleEngine

```python
class TemporalRuleEngine:
    def evaluate(
        self,
        rules: tuple[Rule, ...],
        context: AlignmentContext,
        timeline: TagTimeline,
    ) -> tuple[TagEvent, ...]:
        ...
```

MVP 只支持 `SustainedTagCondition`。

输出 `TagEvent.metadata`：

```python
{
    "rule_kind": "temporal",
    "source_tag": "vehicle_stopped",
    "sustained_frames": 3,
    "supporting_frame_indices": [0, 1, 2],
}
```

## EngineResult

```python
@dataclass(frozen=True)
class EngineStats:
    input_frames: int
    future_frames: int
    single_frame_rules: int
    temporal_rules: int
    events_emitted: int
```

```python
@dataclass(frozen=True)
class EngineDiagnostic:
    level: str
    message: str
    metadata: dict[str, object]
```

```python
@dataclass(frozen=True)
class EngineResult:
    scenario_id: str
    source: str | None
    plan_id: str
    events: tuple[TagEvent, ...]
    stats: EngineStats
    diagnostics: tuple[EngineDiagnostic, ...]
```

## 输出约定

Single-frame TagEvent metadata：

```python
{
    "rule_kind": "single_frame",
    "operator_results": {...},
}
```

Temporal TagEvent metadata：

```python
{
    "rule_kind": "temporal",
    "source_tag": "...",
    "sustained_frames": N,
    "supporting_frame_indices": [...],
}
```

所有 TagEvent 必须携带：

- `scenario_id`
- `source`
- `frame_index`
- `timestamp_seconds`
- `subject_type`
- `subject_id`
- `rule_id`
- `tag_name`
