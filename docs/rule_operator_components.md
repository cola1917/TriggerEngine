# Rule / Operator / TagEvent 组件设计

## 包结构

建议新增：

```text
trigger_engine/
  operators/
    __init__.py
    base.py
    registry.py
    builtins.py
  rules/
    __init__.py
    ast.py
    parser.py
    engine.py
    events.py
    writers.py
```

## operators/base.py

### OperatorResult

```python
@dataclass(frozen=True)
class OperatorResult:
    operator_name: str
    subject_type: str
    subject_id: str | int | None
    frame_index: int
    timestamp_seconds: float
    value: bool | int | float | str
    metadata: dict[str, object]
```

语义：

- operator 计算结果
- 默认只在内存中用于 rule 判断
- `predicate.*` operator 的 `value` 必须是 `bool`
- `metric.*` operator 的 `value` 可以是数值

### Operator

```python
class Operator(Protocol):
    name: str
    result_kind: str
    subject_type: str

    def evaluate(
        self,
        context: AlignmentContext,
        frame: AlignedFrame,
        subject: object,
        args: Mapping[str, object],
    ) -> OperatorResult:
        ...
```

约束：

- operator 只能读取传入的 `AlignmentContext.input_frames` 和当前 `AlignedFrame`
- operator 不应读取 `context.future_frames`
- operator 不负责 rule emit

## operators/registry.py

### OperatorRegistry

```python
class OperatorRegistry:
    def register(self, operator: Operator) -> None:
        ...

    def get(self, name: str) -> Operator:
        ...

    def names(self) -> tuple[str, ...]:
        ...
```

错误：

- 重复注册抛 `OperatorRegistryError`
- 未找到 operator 抛 `OperatorRegistryError`

## rules/ast.py

### RuleSet

```python
@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...]
```

### Rule

```python
@dataclass(frozen=True)
class Rule:
    rule_id: str
    subject_type: str
    condition: Condition
    emit: RuleEmit
    description: str | None = None
    window: RuleWindow | None = None
```

### RuleWindow

```python
@dataclass(frozen=True)
class RuleWindow:
    history_steps: int | None = None
```

### OperatorCall

```python
@dataclass(frozen=True)
class OperatorCall:
    operator_name: str
    args: dict[str, object]
    for_last_n_frames: int | None = None
```

### Condition

MVP 只支持：

```python
@dataclass(frozen=True)
class AllCondition:
    calls: tuple[OperatorCall, ...]
```

未来可增加 `AnyCondition`、`NotCondition`、metric comparator。

### RuleEmit

```python
@dataclass(frozen=True)
class RuleEmit:
    tag_name: str
    value: bool | int | float | str = True
    metadata: dict[str, object] = field(default_factory=dict)
```

## rules/events.py

### TagEvent

```python
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
    metadata: dict[str, object]
```

持久化只依赖这个 schema。

## rules/parser.py

### RuleParser

```python
class RuleParser:
    def parse_yaml(self, text: str) -> RuleSet:
        ...
```

实现约束：

- 使用项目 Python 环境中的 PyYAML 解析 YAML
- MVP parser 只需要支持本文档里的结构化 YAML 子集

校验：

- 顶层必须有 `rules`
- rule id 不能为空且不能重复
- subject 必须是 `frame`、`agent`、`lane`、`scenario`
- MVP 只支持 `when.all`
- operator name 必须是非空字符串
- emit.tag 必须是非空字符串

错误统一抛 `RuleParseError`。

## rules/engine.py

### RuleEngine

```python
class RuleEngine:
    def __init__(self, registry: OperatorRegistry):
        ...

    def evaluate(self, rule_set: RuleSet, context: AlignmentContext) -> tuple[TagEvent, ...]:
        ...
```

执行策略：

1. 遍历 `context.input_frames`
2. 按 rule subject 生成 subjects
   - `agent`: 当前 frame 的 `agent_states`
   - `frame`: 当前 aligned frame
   - `lane`: 当前 frame 的 traffic light lane ids
   - `scenario`: 单个 scenario subject
3. 对每个 subject 评估 `when.all`
4. 所有 predicate operator 返回 `True` 时 emit `TagEvent`
5. `TagEvent.frame_index` 使用当前 `AlignedFrame.frame.step_index`

禁止：

- 不遍历 `context.future_frames`
- 不从 `ScenarioBundle.frames` 重新取帧
- 不让 YAML condition 直接访问 data frame 字段

## rules/writers.py

### JsonlTagEventWriter

```python
class JsonlTagEventWriter:
    def write_many(self, events: Iterable[TagEvent], path: str | Path) -> None:
        ...
```

MVP 可以稍后实现。第一阶段测试只要求 `TagEvent` 可序列化为 dict。
