# 数据处理层组件设计

## 包结构

建议新增包：

```text
trigger_engine/
  __init__.py
  data/
    __init__.py
    frames.py
    adapters.py
    readers.py
    validation.py
```

## frames.py

### Point3D

三维点，字段：

- `x: float`
- `y: float`
- `z: float`

### AgentState

单个 agent 在某一时间步的状态，字段：

- `track_id: int`
- `track_index: int`
- `object_type: str`
- `timestamp_seconds: float`
- `center: Point3D`
- `velocity_x: float`
- `velocity_y: float`
- `heading: float`
- `length: float`
- `width: float`
- `height: float`
- `valid: bool`

枚举归一化：

- `TYPE_UNSET` -> `"unset"`
- `TYPE_VEHICLE` -> `"vehicle"`
- `TYPE_PEDESTRIAN` -> `"pedestrian"`
- `TYPE_CYCLIST` -> `"cyclist"`
- `TYPE_OTHER` -> `"other"`
- 未知值 -> `"unknown"`

### TrafficLightState

交通灯在某一时间步控制某条 lane 的状态，字段：

- `lane_id: int`
- `state: str`
- `stop_point: Point3D | None`

状态归一化：

- `LANE_STATE_UNKNOWN` -> `"unknown"`
- `LANE_STATE_ARROW_STOP` -> `"arrow_stop"`
- `LANE_STATE_ARROW_CAUTION` -> `"arrow_caution"`
- `LANE_STATE_ARROW_GO` -> `"arrow_go"`
- `LANE_STATE_STOP` -> `"stop"`
- `LANE_STATE_CAUTION` -> `"caution"`
- `LANE_STATE_GO` -> `"go"`
- `LANE_STATE_FLASHING_STOP` -> `"flashing_stop"`
- `LANE_STATE_FLASHING_CAUTION` -> `"flashing_caution"`

### MapFeature

静态地图 feature 的统一外壳，字段：

- `feature_id: int`
- `feature_type: str`
- `polyline: tuple[Point3D, ...]`
- `polygon: tuple[Point3D, ...]`
- `properties: dict[str, object]`

约定：

- lane、road_line、road_edge 使用 `polyline`
- crosswalk、speed_bump、driveway 使用 `polygon`
- stop_sign 使用 `properties["position"]` 和 `properties["lane_ids"]`

### PredictionTarget

需要预测的对象，字段：

- `track_index: int`
- `track_id: int`
- `difficulty: str`
- `object_type: str`

### Frame

时间切片，字段：

- `scenario_id: str`
- `step_index: int`
- `timestamp_seconds: float`
- `phase: str`
- `agent_states: tuple[AgentState, ...]`
- `traffic_lights: tuple[TrafficLightState, ...]`

`phase` 取值：

- `"history"`: `step_index < current_time_index`
- `"current"`: `step_index == current_time_index`
- `"future"`: `step_index > current_time_index`

### ScenarioBundle

完整场景，字段：

- `scenario_id: str`
- `timestamps_seconds: tuple[float, ...]`
- `current_time_index: int`
- `sdc_track_index: int`
- `objects_of_interest: tuple[int, ...]`
- `prediction_targets: tuple[PredictionTarget, ...]`
- `frames: tuple[Frame, ...]`
- `map_features: dict[int, MapFeature]`
- `source: str | None`
- `has_lidar_data: bool`

## adapters.py

### WaymoScenarioAdapter

公开 API：

```python
class WaymoScenarioAdapter:
    def from_proto(self, scenario, source: str | None = None) -> ScenarioBundle:
        ...
```

职责：

- 转换 scenario 顶层字段
- 生成每一帧的 `Frame`
- 把 track state 展平到 frame 的 `agent_states`
- 把 dynamic map state 转成 `traffic_lights`
- 把 map feature 转成统一 `MapFeature`
- 建立 prediction target
- 调用 validator

### DataAdapterError

adapter 层统一异常，包含可读错误信息。第一阶段不需要复杂错误码。

## readers.py

### TFRecordScenarioReader

公开 API：

```python
class TFRecordScenarioReader:
    def iter_payloads(self, path: str | Path) -> Iterator[bytes]:
        ...

    def iter_scenarios(self, path: str | Path) -> Iterator[ScenarioBundle]:
        ...
```

第一阶段可以先只实现 `iter_payloads` 和单条读取，`iter_scenarios` 等 protobuf 依赖就绪后再接入。

## validation.py

校验函数：

- `validate_timeline(scenario) -> None`
- `validate_track_lengths(scenario) -> None`
- `validate_indices(scenario) -> None`

策略：

- 结构性错误抛 `DataAdapterError`
- 缺失可选字段使用默认值，不抛异常
- 无效 agent state 保留，不抛异常
