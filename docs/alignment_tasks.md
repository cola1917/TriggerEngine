# Alignment 任务拆分

这是给 worker 执行的任务清单。每完成一项，请把 `[ ]` 改成 `[x]`，并确认对应测试通过。

## Task 1: 建立 alignment 包和上下文 schema

- [x] 创建 `trigger_engine/alignment/__init__.py`
- [x] 创建 `trigger_engine/alignment/context.py`
- [x] 实现 `Watermark`
- [x] 实现 `AlignedFrame`
- [x] 实现 `AlignmentContext`
- [x] 运行 `tests/test_alignment_contract.py`

验收：

- context dataclass contract 测试通过。

## Task 2: 实现基础 ScenarioAlignment

- [x] 创建 `trigger_engine/alignment/scenario_alignment.py`
- [x] 实现 `AlignmentError`
- [x] 实现 `ScenarioAlignment.align`
- [x] watermark 等于 `bundle.current_time_index`
- [x] frame visibility 正确标记为 observed/current/future
- [x] `input_frames` 只包含 observed + current

验收：

- future frame 不会出现在 `input_frames`。
- current frame 与 watermark 对齐。

## Task 3: 实现窗口裁剪

- [x] 支持 `history_steps=None`
- [x] 支持 `future_steps=None`
- [x] 支持 `history_steps=0`
- [x] 支持 `future_steps=0`
- [x] 支持正整数窗口裁剪
- [x] 对负数窗口参数抛 `AlignmentError`

验收：

- observed window 只保留 current 前最近 N 帧。
- future window 只保留 current 后最近 N 帧。

## Task 4: 实现 modality availability

- [x] 标记 `"agents"`
- [x] 标记 `"valid_agents"`
- [x] 标记 `"traffic_lights"`
- [x] 标记 `"map"`
- [x] 标记 `"lidar"`
- [x] lidar 只对 `step_index <= watermark` 的帧可用

验收：

- frame 级 modality 与 bundle/frame 数据一致。
- future frame 即使 bundle 有 lidar，也不标记 lidar。

## Task 5: 实现结构校验

- [x] `bundle.frames` 为空时报 `AlignmentError`
- [x] `current_time_index` 越界时报 `AlignmentError`
- [x] current frame 的 `step_index` 不匹配时报 `AlignmentError`
- [x] 错误消息包含具体字段名

验收：

- 损坏 bundle 的 contract 测试通过。
