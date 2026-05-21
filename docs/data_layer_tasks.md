# 数据处理层任务拆分

这是给 worker 执行的任务清单。每完成一项，请把 `[ ]` 改成 `[x]`，并在 PR 或提交说明里写清楚对应测试。

## Task 1: 建立包结构和 schema

- [x] 创建 `trigger_engine/__init__.py`
- [x] 创建 `trigger_engine/data/__init__.py`
- [x] 创建 `trigger_engine/data/frames.py`
- [x] 在 `frames.py` 中实现 `Point3D`
- [x] 在 `frames.py` 中实现 `AgentState`
- [x] 在 `frames.py` 中实现 `TrafficLightState`
- [x] 在 `frames.py` 中实现 `MapFeature`
- [x] 在 `frames.py` 中实现 `PredictionTarget`
- [x] 在 `frames.py` 中实现 `Frame`
- [x] 在 `frames.py` 中实现 `ScenarioBundle`
- [x] 运行 `python -m unittest discover -s tests -v`

验收：

- `tests/test_frame_schema_contract.py` 通过。
- dataclass 字段名与设计文档一致。

## Task 2: 实现 WaymoScenarioAdapter 基础转换

- [x] 创建 `trigger_engine/data/adapters.py`
- [x] 实现 `DataAdapterError`
- [x] 实现 `WaymoScenarioAdapter.from_proto`
- [x] 转换 scenario 元数据
- [x] 转换 track states 到每一帧的 `agent_states`
- [x] 实现 object type 枚举归一化
- [x] 实现 frame `phase` 判定
- [x] 运行 adapter contract 测试

验收：

- fake scenario 不依赖 protobuf，可以完成转换。
- `current_time_index` 前后帧 phase 正确。
- 无效 state 被保留。

## Task 3: 实现动态地图和预测目标

- [x] 转换 `dynamic_map_states[*].lane_states`
- [x] 实现 traffic light state 枚举归一化
- [x] 转换 `tracks_to_predict`
- [x] `PredictionTarget.track_id` 从 `tracks[track_index].id` 取得
- [x] 运行全部测试

验收：

- 每个 frame 有对应时间步的 `traffic_lights`。
- prediction target 包含 track index、track id、object type、difficulty。

## Task 4: 实现静态地图 feature 转换

- [x] 转换 lane polyline 和属性
- [x] 转换 road_line polyline 和属性
- [x] 转换 road_edge polyline 和属性
- [x] 转换 crosswalk polygon
- [x] 转换 speed_bump polygon
- [x] 转换 stop_sign position 和 lane ids
- [x] 转换 driveway polygon

验收：

- `ScenarioBundle.map_features` 以 feature id 为 key。
- 不同 map feature 类型都能落入统一 `MapFeature`。

## Task 5: 实现校验

- [x] 创建 `trigger_engine/data/validation.py`
- [x] 校验时间轴非空
- [x] 校验 `current_time_index` 范围
- [x] 校验每个 track 的 states 长度
- [x] 校验 `dynamic_map_states` 长度
- [x] 校验 `sdc_track_index`
- [x] 校验 `tracks_to_predict[*].track_index`
- [x] 给错误写清晰消息

验收：

- 损坏 scenario 的测试抛 `DataAdapterError`。
- 错误消息包含具体字段名。

## Task 6: 接入 reader

- [x] 创建 `trigger_engine/data/readers.py`
- [x] 复用或迁移 `inspect_frame.read_tfrecord`
- [x] 实现 `TFRecordScenarioReader.iter_payloads`
- [x] 在 protobuf 可用时实现 `iter_scenarios`
- [x] 保持 `inspect_frame.py` 现有测试通过

验收：

- reader 可以读取 TFRecord payload。
- protobuf 缺失时错误清楚，不影响纯 schema/adapter 单测。
