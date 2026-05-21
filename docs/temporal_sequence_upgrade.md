# Temporal Sequence Upgrade 设计

## 背景

当前 temporal rule 只支持：

```yaml
when:
  tag: vehicle_stopped
  sustained:
    frames: 3
```

这适合“持续 N 帧”，但无法表达 cut-in 的核心过程：

```text
先在侧方/不同路径
再横向靠近
再进入同一路径/同车道近似
随后伴随 low TTC 或 ego braking
```

因此需要给 temporal rule 增加 sequence 表达。

## 目标

新增 temporal sequence DSL：

```yaml
rules:
  - id: cut_in_confirmed
    kind: temporal
    subject: agent_pair
    when:
      sequence:
        - tag: adjacent_vehicle
        - tag: same_path_overlap
      within_frames: 10
    emit:
      tag: cut_in_confirmed
```

语义：

- 对同一个 `subject_type + subject_id`
- 在当前 frame 结束的最近 `within_frames` 内
- 按顺序出现指定 tag
- 允许中间有空帧
- 输出时记录每个 step 匹配到的 frame index

## AST 扩展

```python
@dataclass(frozen=True)
class SequenceStep:
    tag_name: str

@dataclass(frozen=True)
class SequenceTagCondition:
    steps: tuple[SequenceStep, ...]
    within_frames: int
```

`Rule.condition` 支持：

```python
AllCondition
SustainedTagCondition
SequenceTagCondition
```

## Compiler 校验

`RuleCompiler` 对 sequence rule 校验：

- `kind` 必须是 `"temporal"`
- `sequence` 至少有两个 step
- `within_frames` 必须是正整数
- 每个 step 的 tag 必须来自同 plan 中已定义的 single-frame emit tag
- 每个 step tag 的 subject 必须与 temporal rule subject 一致
- sequence rule 不允许直接引用 operator

## TagTimeline 扩展

新增：

```python
def sequence(
    self,
    keys: tuple[TagKey, ...],
    end_frame_index: int,
    within_frames: int,
) -> tuple[bool, tuple[int, ...]]:
    ...
```

匹配策略：

- 搜索窗口：`[end_frame_index - within_frames + 1, end_frame_index]`
- 每个 step 必须按顺序匹配到一个 frame
- 后一个 step 的 frame index 必须大于等于前一个 step
- 返回 step 对应的 supporting frame indices

## Cut-in Rule 优化方向

新增单帧 tags：

```text
adjacent_vehicle
lateral_motion_toward
same_path_overlap
low_ttc_pair
```

第一版 cut-in confirmed：

```yaml
- id: cut_in_confirmed
  kind: temporal
  subject: agent_pair
  when:
    sequence:
      - tag: adjacent_vehicle
      - tag: lateral_motion_toward
      - tag: same_path_overlap
    within_frames: 10
  emit:
    tag: cut_in_confirmed
```

风险增强：

```yaml
- id: cut_in_risk
  kind: temporal
  subject: agent_pair
  when:
    sequence:
      - tag: cut_in_confirmed
      - tag: low_ttc_pair
    within_frames: 3
  emit:
    tag: cut_in_risk
```

后续如果要表达 ego braking，需要引入 subject 映射：

```text
agent_pair:ego -> agent
```

这不放入本次 MVP。

## 输出 metadata

sequence temporal TagEvent：

```python
{
    "rule_kind": "temporal",
    "temporal_kind": "sequence",
    "source_tags": ["adjacent_vehicle", "same_path_overlap"],
    "within_frames": 10,
    "supporting_frame_indices": (3, 8),
}
```

## 非目标

- 不做任意正则/复杂 CEP
- 不做跨 subject 映射，例如 pair ego 对 agent brake
- 不做 lane graph 同车道判断
- 不让 temporal rule 直接引用 operator
