# Scenario Packs 组件设计

## 包结构

建议新增：

```text
trigger_engine/
  operators/
    builtins.py
  scenarios/
    __init__.py
    classic.py
```

## operators/builtins.py

### register_builtin_operators

```python
def register_builtin_operators(registry: OperatorRegistry) -> None:
    ...
```

注册基础算子：

- `predicate.type_is`
- `predicate.speed_below`
- `predicate.speed_above`
- `predicate.pair_types_are`
- `predicate.pair_in_front`
- `predicate.low_ttc`
- `predicate.close_lateral_gap`
- `predicate.lateral_motion_toward`
- `predicate.heading_converging`
- `predicate.near_red_light_stop_point`

重复注册策略：

- 如果同名 operator 已存在，跳过
- 不覆盖已有 operator

## AgentPairSubject

```python
@dataclass(frozen=True)
class AgentPairSubject:
    ego: AgentState
    other: AgentState

    @property
    def subject_id(self) -> str:
        return f"{self.ego.track_id}:{self.other.track_id}"
```

`RuleEngine` 需要支持：

```text
subject: agent_pair
```

subject 生成策略：

- 从当前 frame 的 valid agent states 生成有序 pair
- 排除相同 track
- 第一阶段可接受 O(N^2)
- 后续再加 spatial pruning

## Built-in operators

### predicate.type_is

subject: `agent`

args:

- `object_type: str`

返回：

- `subject.object_type == object_type`

### predicate.speed_below / predicate.speed_above

subject: `agent`

args:

- `threshold_mps: float`

速度：

```python
sqrt(vx * vx + vy * vy)
```

无效 state 返回 `False`。

### predicate.pair_types_are

subject: `agent_pair`

args:

- `ego_type: str | None`
- `other_type: str | None`

如果参数为 `null`，则不约束对应类型。

### predicate.pair_in_front

subject: `agent_pair`

args:

- `min_longitudinal_m: float = 0.0`
- `max_lateral_m: float = 4.0`

基于 ego heading 将 relative vector 投影到 ego local frame。

### predicate.low_ttc

subject: `agent_pair`

args:

- `threshold_s: float`
- `max_lateral_m: float = 4.0`
- `min_closing_speed_mps: float = 0.1`

计算：

```text
longitudinal_gap / closing_speed
```

只在 other 位于 ego 前方且 lateral gap 小于阈值时返回 true。

### predicate.close_lateral_gap

subject: `agent_pair`

args:

- `max_lateral_m: float`
- `max_longitudinal_m: float`

### predicate.lateral_motion_toward

subject: `agent_pair`

args:

- `min_lateral_speed_mps: float`

判断 other 的横向相对速度是否朝 ego 方向。

### predicate.heading_converging

subject: `agent_pair`

args:

- `min_heading_delta_rad: float`
- `max_heading_delta_rad: float`

### predicate.near_red_light_stop_point

subject: `agent`

args:

- `max_distance_m: float`

逻辑：

- 查找当前 frame 的 traffic lights
- 状态属于 `stop` 或 `arrow_stop`
- 有 stop_point
- agent center 到 stop_point 距离小于阈值

## scenarios/classic.py

### CLASSIC_SCENARIO_RULES_YAML

包含四类规则：

- Stopped Vehicle
- Low TTC
- Cut-in Candidate
- Traffic Light Interaction

### register_classic_scenario_pack

```python
def register_classic_scenario_pack(
    operator_registry: OperatorRegistry,
    rule_registry: RuleRegistry,
    plan_id: str = "classic_v1",
) -> ExecutionPlan:
    register_builtin_operators(operator_registry)
    plan = rule_registry.register_yaml(plan_id, CLASSIC_SCENARIO_RULES_YAML)
    rule_registry.activate(plan_id)
    return plan
```

## YAML DSL

`CLASSIC_SCENARIO_RULES_YAML` 应使用现有 DSL：

- `kind: single_frame`
- `kind: temporal`
- `subject: agent`
- `subject: agent_pair`
- `when.all`
- `when.tag + sustained.frames`

不新增 DSL 语法。

## 输出示例

```text
vehicle_stopped
persistent_low_ttc_pair
cut_in_developing
vehicle_still_stopped_at_red
```

每个输出都是 `TagEvent`。
