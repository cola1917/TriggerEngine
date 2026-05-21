# Scenario Packs 架构设计

## 目标

Scenario Pack 是一组可复用的场景能力包，包含：

- built-in operators
- YAML DSL rules
- 可选默认阈值
- 输出 TagEvent 约定

本阶段实现四类高价值经典场景：

1. Stopped Vehicle / Long Stop
2. Low TTC / Collision Risk
3. Cut-in Candidate
4. Traffic Light Interaction

## 接入位置

```text
OperatorRegistry
  <- register_builtin_scenario_operators()

RuleRegistry
  <- register_yaml("classic_v1", CLASSIC_SCENARIO_RULES_YAML)

AlignmentContext
  -> TriggerEngine.evaluate(context)
  -> TagEvent
```

Scenario Pack 不修改 core engine 的运行模型。它只是向既有系统注册能力和规则。

## Subject 类型扩展

现有 subject：

- `frame`
- `agent`
- `lane`
- `scenario`

本场景包建议新增：

- `agent_pair`

`agent_pair` 表示同一 frame 内两个 agent 的有序组合：

```python
AgentPairSubject(
    ego: AgentState,
    other: AgentState,
)
```

约定：

- `subject_id == "{ego.track_id}:{other.track_id}"`
- pair 不跨 frame
- 默认不生成 `ego == other`
- pair operator 的 `subject_type` 为 `"agent_pair"`

新增 `agent_pair` 的原因：

- Low TTC 是 pairwise 风险
- Cut-in 是 pairwise 交互
- 不应该把 pair 逻辑硬塞进单 agent operator

## 四类场景

### 1. Stopped Vehicle / Long Stop

单帧 tag：

- `vehicle_stopped`

时序 tag：

- `vehicle_stopped_for_3_frames`

operators：

- `predicate.type_is`
- `predicate.speed_below`

YAML：

```yaml
- id: vehicle_stopped
  kind: single_frame
  subject: agent
  when:
    all:
      - operator: predicate.type_is
        args:
          object_type: vehicle
      - operator: predicate.speed_below
        args:
          threshold_mps: 0.5
  emit:
    tag: vehicle_stopped

- id: vehicle_stopped_for_3_frames
  kind: temporal
  subject: agent
  when:
    tag: vehicle_stopped
    sustained:
      frames: 3
  emit:
    tag: vehicle_stopped_for_3_frames
```

### 2. Low TTC / Collision Risk

单帧 tag：

- `low_ttc_pair`

时序 tag：

- `persistent_low_ttc_pair`

operators：

- `predicate.pair_types_are`
- `predicate.pair_in_front`
- `predicate.low_ttc`

语义：

- pair 中 `other` 在 `ego` 前方
- closing speed 大于 0
- TTC 小于阈值

输出 subject：

```text
subject_type=agent_pair
subject_id="{ego_id}:{other_id}"
```

### 3. Cut-in Candidate

单帧 tag：

- `cut_in_candidate`

时序 tag：

- `cut_in_developing`

operators：

- `predicate.pair_types_are`
- `predicate.close_lateral_gap`
- `predicate.lateral_motion_toward`
- `predicate.heading_converging`

MVP 几何近似：

- 不做 lane matching
- 基于 relative position、relative velocity、heading 差判断
- 适合先做候选挖掘，不作为最终安全判定

输出 subject：

```text
subject_type=agent_pair
subject_id="{ego_id}:{other_id}"
```

### 4. Traffic Light Interaction

单帧 tag：

- `vehicle_stopped_at_red`
- `vehicle_moving_on_red_candidate`

时序 tag：

- `vehicle_still_stopped_at_red`

operators：

- `predicate.type_is`
- `predicate.speed_below`
- `predicate.speed_above`
- `predicate.near_red_light_stop_point`

MVP 近似：

- 不做 lane graph 匹配
- 使用 dynamic map state 的 `stop_point`
- agent center 到 red/arrow_stop traffic light stop_point 距离小于阈值

输出 subject：

```text
subject_type=agent
subject_id=track_id
```

## 输出 TagEvent 约定

所有 scenario pack 输出必须使用 `TagEvent`：

```python
TagEvent(
    scenario_id=...,
    source=...,
    frame_index=...,
    timestamp_seconds=...,
    tag_name=...,
    subject_type="agent" | "agent_pair",
    subject_id=...,
    value=True,
    rule_id=...,
    metadata={
        "rule_kind": "single_frame" | "temporal",
        ...
    },
)
```

pair event metadata 建议包含：

```python
{
    "ego_track_id": 100,
    "other_track_id": 200,
}
```

operator metadata 建议包含计算值：

- speed
- distance
- ttc
- lateral_gap
- heading_delta
- distance_to_stop_point

## 第一阶段非目标

- 不做精确 lane assignment
- 不做 HD map topology query
- 不做 SDC 专用规则
- 不做真实 collision geometry
- 不做 sequence DSL，只做 sustained temporal rule

## 验收标准

- classic scenario rule YAML 可由 RuleParser 解析
- RuleCompiler 能校验并生成 plan
- built-in operators 可注册到 OperatorRegistry
- TriggerEngine 能对 fake AlignmentContext 输出四类 tag
- `agent_pair` 不跨 subject 拼接 temporal tags
- future frame 不进入 scenario pack 输出
