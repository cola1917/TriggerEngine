# Alignment 组件设计

## 包结构

建议新增：

```text
trigger_engine/
  alignment/
    __init__.py
    context.py
    scenario_alignment.py
```

## context.py

### Watermark

```python
@dataclass(frozen=True)
class Watermark:
    scenario_id: str
    step_index: int
    timestamp_seconds: float
```

语义：

- 当前可观测边界
- 离线 Waymo scenario 中等于 `current_time_index`

### AlignedFrame

```python
@dataclass(frozen=True)
class AlignedFrame:
    frame: Frame
    visibility: str
    available_modalities: frozenset[str]
```

`visibility` 取值：

- `"observed"`
- `"current"`
- `"future"`

### AlignmentContext

```python
@dataclass(frozen=True)
class AlignmentContext:
    scenario_id: str
    watermark: Watermark
    observed_frames: tuple[AlignedFrame, ...]
    current_frame: AlignedFrame
    future_frames: tuple[AlignedFrame, ...]
    input_frames: tuple[AlignedFrame, ...]
    source: str | None = None
```

约定：

- `input_frames == observed_frames + (current_frame,)`
- `future_frames` 不出现在 `input_frames`
- `source` 从 `ScenarioBundle.source` 传入，用于后续 `TagEvent` 持久化定位原始文件

## scenario_alignment.py

### AlignmentError

alignment 层统一异常。

### ScenarioAlignment

公开 API：

```python
class ScenarioAlignment:
    def align(
        self,
        bundle: ScenarioBundle,
        history_steps: int | None = None,
        future_steps: int | None = None,
    ) -> AlignmentContext:
        ...
```

参数：

- `bundle`: data layer 输出的完整 scenario
- `history_steps`: 只保留 current 前最近 N 帧；`None` 表示保留全部历史
- `future_steps`: 只保留 current 后最近 N 帧；`None` 表示保留全部未来

校验：

- `bundle.frames` 不能为空
- `bundle.current_time_index` 必须落在 `bundle.frames` 范围内
- `bundle.frames[bundle.current_time_index].step_index` 必须等于 `bundle.current_time_index`
- `history_steps` 和 `future_steps` 如果传入，必须大于等于 0

模态识别：

```python
def available_modalities(bundle, frame) -> frozenset[str]:
    modalities = set()
    if frame.agent_states:
        modalities.add("agents")
    if any(agent.valid for agent in frame.agent_states):
        modalities.add("valid_agents")
    if frame.traffic_lights:
        modalities.add("traffic_lights")
    if bundle.map_features:
        modalities.add("map")
    if bundle.has_lidar_data and frame.step_index <= bundle.current_time_index:
        modalities.add("lidar")
    return frozenset(modalities)
```

## 与 data layer 的关系

Data layer 负责把原始数据转成稳定 schema。Alignment 只读取：

- `ScenarioBundle.scenario_id`
- `ScenarioBundle.current_time_index`
- `ScenarioBundle.frames`
- `ScenarioBundle.map_features`
- `ScenarioBundle.has_lidar_data`
- `Frame.step_index`
- `Frame.timestamp_seconds`
- `Frame.agent_states`
- `Frame.traffic_lights`

这样 alignment 对 Waymo proto 零依赖。
