# TriggerEngine 第二数据源适配分析

## 概述

当前 TriggerEngine 仅支持 Waymo Open Dataset。本文档分析：如果接入第二个数据源（如 nuScenes、Argoverse 2、或内部车队数据），哪些模块需要改动、改动量多大、以及当前架构的哪些"假解耦"会被暴露。

---

## 1. 当前耦合全景图

### 1.1 Waymo 耦合热力图

```
                    直接耦合 Waymo    有抽象但只有      完全数据源无关
                    无抽象层          一个实现

data/adapters.py        ████████████
data/readers.py         ████████████
data/validation.py      ██████
data/frames.py          ████████        ████
alignment/context.py    ████            ████████
alignment/scenario*.py  ████████        ████
engine/subjects.py      ██              ██████          ████
engine/trigger_engine.py  ██            ██████          ████
engine/timeline.py                                    ████████████
engine/event_policy.py                                 ████████████
engine/compiler.py                                     ████████████
engine/registry.py                                     ████████████
rules/parser.py                                        ████████████
rules/ast.py                                           ████████████
rules/engine.py          ██                            ██████████
rules/events.py                                        ████████████
operators/builtins.py    ████            ████           ████
operators/lane_match.py  ████            ████           ████
operators/base.py                                      ████████████
operators/registry.py                                  ████████████
scenarios/classic.py                                   ████████████
```

**结论：耦合集中在 data/ 和 alignment/ 两个"薄层"，但 operators/ 对数据格式有隐式依赖。**

### 1.2 分层看耦合

#### 第一层：硬编码 Waymo Protobuf 的地方

| 位置 | 耦合内容 | 严重程度 |
|------|---------|---------|
| `data/readers.py` | TFRecord 二进制格式 | 🔴 完全 Waymo 专用 |
| `data/adapters.py` | `scenario_pb2.Scenario` protobuf 解析 | 🔴 完全 Waymo 专用 |
| `data/adapters.py` | Waymo 枚举映射表（object_type, lane_state, road_line_type 等） | 🔴 完全 Waymo 专用 |
| `data/validation.py` | 验证逻辑依赖 Waymo 数据结构（tracks, timestamps_seconds, dynamic_map_states） | 🟡 概念通用，但字段名耦合 |

#### 第二层：ScenarioBundle/Frames 数据结构

| 字段 | Waymo 特性 | 其他数据源有吗 |
|------|-----------|-------------|
| `scenario_id: str` | Waymo 的 scenario 是 9 秒切片 | nuScenes 用 scene/sample token，语义不同 |
| `timestamps_seconds` | 固定 10Hz，91 帧 | nuScenes 是 2Hz 关键帧 + 10Hz 插值；Argoverse 是 10Hz |
| `current_time_index` | Waymo 将 9 秒窗口的第 1 秒作为 history | 其他数据集没有这个概念 |
| `sdc_track_index` | Waymo 专门标记自车 track | 其他数据集有 ego 概念但表示方式不同 |
| `objects_of_interest` | Waymo 特定 | nuScenes/Argoverse 没有 |
| `prediction_targets` | Waymo 运动预测任务的 track 列表 | Argoverse 有，nuScenes 有但格式不同 |
| `has_lidar_data` | 单一布尔值 | 其他数据源可能有 camera/radar/lidar 多模态 |
| `map_features: dict[int, MapFeature]` | Waymo 的地图用 polyline/polygon + feature_type 枚举 | nuScenes 用 lane graph，Argoverse 用 vector map |

#### 第三层：AgentState 字段隐式假设

```python
class AgentState:
    track_id: int           # ← 假设 track_id 是整数。nuScenes 用 token (字符串)
    track_index: int        # ← 纯 Waymo 概念（tracks 数组索引）
    object_type: str        # ← 枚举值耦合 Waymo 分类
    timestamp_seconds: float
    center: Point3D         # ← 坐标系耦合（Waymo 用场景中心坐标系）
    velocity_x: float       # ← 速度参考系耦合
    velocity_y: float
    heading: float          # ← 方向定义耦合
    length: float
    width: float
    height: float
    valid: bool             # ← Waymo tracks 可能有无效时间步
```

**在其他数据源中：**
- nuScenes 用 **全局坐标系** + **instance_token**（字符串）而非 track_id
- nuScenes 的 annotation 是稀疏的（只有关键帧有），中间帧需要插值
- Argoverse 的 agent 类型枚举不同（`VEHICLE` / `PEDESTRIAN` / `CYCLIST` / `MOTORCYCLIST` / `BUS` / …）
- 内部车队数据可能没有 `valid` 标志——所有数据都是有效的

#### 第四层：operators/builtins.py 的隐式依赖（最关键！）

虽然算子通过 Protocol 接口定义（看起来解耦了），但实际上 **2072 行 builtins.py 大量直接访问 `AgentState` 的具体字段**：

```python
# 这些字段名在 2072 行代码中出现上百次
agent.center.x          # ← 假设有 .center 属性，类型是 Point3D
agent.center.y
agent.velocity_x        # ← 假设有标量速度分量
agent.velocity_y
agent.heading           # ← 假设有 heading 属性
agent.track_id          # ← 假设 track_id 是 int，用作比较和标识
agent.valid             # ← 假设有 valid 属性
agent.length / .width   # ← 假设有尺寸属性

# 地图查询依赖
frame.frame.traffic_lights       # ← 假设每帧有 traffic_lights
tl.state in {"stop", "arrow_stop"}  # ← 状态枚举值耦合 Waymo
tl.stop_point                     # ← Waymo 特定
context.map_features              # ← 假设地图是 dict[int, MapFeature]
feature.feature_type == "lane"    # ← 类型枚举耦合
feature.polyline                  # ← 假设 polyline 表示
```

**这意味着：** 换一个数据源，如果新的数据格式不能直接提供这些字段名，**所有算子都需要适配**——不是改算子逻辑，而是算子访问的数据对象必须保持相同的"鸭子类型"。

---

## 2. 以 nuScenes 为例：逐层冲击分析

### 2.1 nuScenes 与 Waymo 的关键差异

| 维度 | Waymo | nuScenes | 适配难度 |
|------|-------|---------|---------|
| **数据格式** | TFRecord + Protobuf | SQLite + JSON table | 🔴 完全不同 |
| **时间结构** | 9 秒 91 帧 (10Hz) 连续 | 20 秒 scene，2Hz 关键帧，中间需插值 | 🟡 需要插值或改变帧模型 |
| **时间切片** | scenario 自带 current_time_index | scene 是连续长片段，需自行切片 | 🟡 需要新增切片逻辑 |
| **自车标识** | `sdc_track_index` (整数) | `ego` 直接标注在 sample 上 | 🟢 语义相似 |
| **Agent ID** | `track_id: int` | `instance_token: str` | 🟡 ID 类型从 int 变 str |
| **Agent 类型** | 4 类 (vehicle/pedestrian/cyclist/other) | 更细粒度 | 🟢 可映射 |
| **坐标系** | 场景中心坐标系 | 全局 UTM 坐标系 | 🟡 需要坐标转换 |
| **地图格式** | Polyline + Polygon (protobuf) | Lane graph (节点+边，JSON) | 🔴 完全不同 |
| **交通灯** | 每帧每个 lane 的状态 + stop_point | 交通灯作为独立 annotation | 🔴 模型完全不同 |
| **传感器** | LiDAR 为主 | Camera + Radar + LiDAR | 🟢 仅影响 modalities 标记 |
| **速度表示** | 标量 `velocity_x/y` | `translation` 差分 / `velocity` token | 🟡 需计算 |
| **有效标志** | `valid: bool` (track 有无效帧) | 无此概念 | 🟢 可默认 True |

### 2.2 逐文件改动清单

#### 🔴 必须重写

| 文件 | 当前行数 | 改动说明 |
|------|---------|---------|
| `data/readers.py` | 63 | TFRecord 读取 → SQLite/JSON 读取。**整个替换** |
| `data/adapters.py` | 285 | `WaymoScenarioAdapter` → 新增 `NuScenesAdapter`。大约 200-300 行新代码 |

#### 🟡 需要结构性改动

| 文件 | 改动说明 |
|------|---------|
| `data/frames.py` | `AgentState.track_index` 在 nuScenes 中没有对应概念，需改为可选。`traffic_lights` 模型可能需要泛化。估算：20-40 行改动 |
| `data/validation.py` | 当前验证依赖 Waymo 的 `tracks`/`timestamps_seconds`/`dynamic_map_states` 字段。需要让验证逻辑变成可选或用 Protocol 泛化。估算：30 行改动 |
| `alignment/scenario_alignment.py` | nuScenes 没有 `current_time_index`，需要自己切片。需要新增 scene→scenario 切分逻辑。`has_lidar_data` → 多模态标记。估算：50-80 行新增 |
| `alignment/context.py` | `sdc_track_index: int` 只在 Waymo 中有用，需改为可选或改名为 `ego_track_id`。估算：10 行改动 |

#### 🟢 需要适配但改动可控

| 文件 | 改动说明 |
|------|---------|
| `operators/builtins.py` (2072 行) | 算子访问 `agent.center.x`、`agent.velocity_x` 等。只要新的 AgentState 保持相同字段名，算子代码**不用改**。但需要确保 nuScenes 适配器正确填充这些字段。估算：0 行（如果适配器做得好） |
| `operators/lane_matching.py` (260 行) | 当前依赖 `MapFeature.polyline`。nuScenes 的 lane graph 是节点+边，需要转换成 polyline 或修改匹配逻辑。**这是最硬的地图问题。** 估算：可能需要 50-100 行新增或新的 `NuScenesLaneMatcher` |
| `engine/subjects.py` (682 行) | `sdc_track_id` 硬编码出现 10+ 次。如果统一改为 `ego_track_id`，改动约 20 处。如果是 `sdc_pair` 语义，nuScenes 一样适用，只是改参数名 |
| `rules/engine.py` (269 行) | `sdc_track_id` 硬编码出现 4 次。同上 |
| `engine/trigger_engine.py` (516 行) | `sdc_track_id` 出现 3 次。同上 |

#### ⚪ 基本不用改

| 文件 | 原因 |
|------|------|
| `rules/parser.py` | 解析的是 YAML，与数据源无关 |
| `rules/ast.py` | 纯数据结构 |
| `rules/events.py` | TagEvent 是引擎内部概念 |
| `rules/writers.py` | 输出 JSONL，与输入无关 |
| `engine/timeline.py` | 纯内存索引结构 |
| `engine/event_policy.py` | 只操作 TagEvent |
| `engine/compiler.py` | 只操作算子注册表和 AST |
| `engine/registry.py` | 只管理 ExecutionPlan |
| `operators/base.py` | Protocol 定义 |
| `operators/registry.py` | 只管理算子注册 |
| `scenarios/classic.py` | YAML 规则定义，可能某些规则对 nuScenes 不适用但不需要改代码 |

### 2.3 改动量估算

| 层级 | 新增代码 | 修改代码 | 风险等级 |
|------|---------|---------|---------|
| 新 Adapter | ~300 行 | 0 | 🟢 纯增量 |
| 新 Reader | ~80 行 | 0 | 🟢 纯增量 |
| frames.py | 0 | ~30 行 | 🟡 向后兼容 |
| alignment | ~80 行 | ~30 行 | 🟡 需保持 Waymo 路径不变 |
| subjects.py | 0 | ~20 行 | 🟡 `sdc_*` → `ego_*` 重命名 |
| rules/engine.py | 0 | ~5 行 | 🟢 |
| trigger_engine.py | 0 | ~5 行 | 🟢 |
| lane_matching.py | ~100 行 | 0 | 🟡 新地图表示 |
| **合计** | **~560 行** | **~90 行** | |

**占核心总代码量（6,258 行）的比例：约 10%**

---

## 3. 真正需要抽象的接口

当前没有任何形式化的 Adapter 接口。如果要真正支持多数据源，至少需要：

### 3.1 ScenarioAdapter Protocol

```python
class ScenarioAdapter(Protocol):
    """将外部数据格式转换为统一的 ScenarioBundle。

    每个数据源实现一个 Adapter。
    """
    def load(self, source: str | Path) -> ScenarioBundle: ...

    @property
    def source_type(self) -> str: ...
    # 例如 "waymo_v1", "nuscenes_v1", "argoverse_v2"
```

当前 `WaymoScenarioAdapter.from_proto(scenario, source)` 的参数签名是 Waymo 专用的（接收 protobuf 对象）。需要一个通用入口。

### 3.2 坐标系统一

Waymo 用**场景中心坐标系**（原点在每个 scenario 的 SDC 起始位置）。nuScenes 用**全局 UTM 坐标系**。

Agent 的 `center.x/y` 和 `velocity_x/y` 在不同坐标系下数值完全不同。但算子（如 TTC 计算、车道匹配）依赖的是**相对**位置和速度——只要同一帧的所有 agent 在同一个坐标系下，算子就能正常工作。

**设计决策：** 不在算子层做坐标转换，而是在 Adapter 层将数据统一到"场景局部坐标系"（如以当前帧 SDC 位置为原点）。每个 Adapter 负责自己的坐标归一化。

### 3.3 地图特征泛化

当前 `MapFeature` 用 `polyline` 表示所有地图元素。nuScenes 的 lane graph 不是 polyline 集合，而是拓扑结构（lane 之间的连接关系）。

**方案 A：Adatper 层做转换。** NuScenesAdapter 将 lane graph "展开"为 polyline，填入 `MapFeature`。优点：lane_matching 算子不用改。缺点：丢失了拓扑信息。

**方案 B：MapFeature 支持多种表示。** 
```python
@dataclass(frozen=True)
class MapFeature:
    feature_id: int | str            # ← ID 类型放宽
    feature_type: str
    polyline: tuple[Point3D, ...]    # 线表示（保留）
    polygon: tuple[Point3D, ...]     # 面表示（保留）
    graph_edges: tuple[...]          # 图表示（新增）
    properties: dict[str, object]
```

方案 B 更灵活但改动大。对于当前的规则集（只用 polyline 做车道匹配），方案 A 足够。

### 3.4 Agent ID 类型泛化

当前 `track_id: int` 出现在约 60+ 处。nuScenes 用 `instance_token: str`。

**方案：** `track_id: int | str`。Python 的 `int | str` 类型比较和哈希都是合法的。需要检查的地方：
- `subject_id` 构建（如 `f"{ego.track_id}:{other.track_id}"`）——对字符串仍然有效
- 排序（`sorted(ids, key=str)`）——已有 `key=str`，兼容
- JSON 序列化——`int` 和 `str` 都合法

**风险：** `subject_id` 的冒号分隔逻辑（`parts = subject_id.split(":", 1)`）在 nuScenes 的 token 中可能遇到 token 本身含冒号的情况。需要选一个不会出现在 token 中的分隔符，或用 tuple 做 key。

### 3.5 SDC → Ego 重命名

当前 `sdc_*` 硬编码在整个引擎中（`sdc_track_id`, `sdc_track_index`, `sdc_agent`, `sdc_pair`）。"SDC" 是 Waymo 的术语（Self-Driving Car）。nuScenes 和 Argoverse 也有自车概念，但叫法不同。

**最小改动方案：** 不改 YAML DSL 中的 `subject` 名称，只在 Adapter 层将 nuScenes 的 ego 映射为 `sdc_track_id`。DSL 中的 `subject: sdc_pair` 对 nuScenes 同样有效——语义是"自车和其他 agent 的 pair"。

**但如果接入的是非自车场景**（如路口视角，没有明确的 ego），`sdc_*` 的概念就不适用了。届时需要新增 `ego_agent`/`ego_pair` 作为更通用的名称，`sdc_*` 保留作为别名。

---

## 4. 接入 nuScenes 的具体技术方案

### 4.1 整体架构

```
nuScenes SQLite DB
  │
  ▼ NuScenesReader
scene JSON + sample_annotation JSON
  │
  ▼ NuScenesAdapter
ScenarioBundle  ←────── 与 Waymo 路径在此汇合
  │
  ▼ ScenarioAlignment
AlignmentContext
  │
  ▼ TriggerEngine  ←────── 完全不变
```

### 4.2 NuScenesReader 设计

nuScenes 的数据在 SQLite 数据库中：
- `scene` 表：scene 描述（20 秒长，包含 first/last sample token）
- `sample` 表：关键帧（2Hz），包含 ego_pose、timestamp
- `sample_annotation` 表：每个关键帧的 agent 标注
- `ego_pose` 表：自车全局位姿
- `map` 表：地图（lane graph 格式）

```python
class NuScenesReader:
    def __init__(self, dataroot: str):
        self.nusc = NuScenes(version='v1.0-trainval', dataroot=dataroot)

    def iter_scenes(self) -> Iterator[dict]:
        """将 nuScenes scene 转为与 ScenarioBundle 兼容的中间格式"""
        for scene in self.nusc.scene:
            samples = self._get_scene_samples(scene)
            yield {
                "scene_token": scene['token'],
                "samples": samples,  # 关键帧列表
                "ego_poses": self._get_ego_poses(scene),
                "map_data": self._get_map_for_scene(scene),
            }
```

### 4.3 NuScenesAdapter 核心逻辑

```python
class NuScenesAdapter:
    def to_scenario_bundle(self, scene_data: dict) -> ScenarioBundle:
        # 1. 将 2Hz 关键帧插值到 10Hz
        frames = self._interpolate_frames(
            scene_data["samples"],
            target_hz=10,
        )

        # 2. 坐标系转换：全局 UTM → 场景局部坐标系
        ego_start_pose = scene_data["ego_poses"][0]
        frames = self._transform_to_local(frames, origin=ego_start_pose)

        # 3. Agent ID 映射：instance_token (str) → track_id (int)
        #    使用哈希或简单递增映射
        agent_id_map = self._build_agent_id_map(frames)

        # 4. 地图转换：lane graph → polyline MapFeature
        map_features = self._lane_graph_to_polylines(
            scene_data["map_data"]
        )

        # 5. 组装 ScenarioBundle（保持与 Waymo 路径完全一致的输出结构）
        return ScenarioBundle(
            scenario_id=scene_data["scene_token"],
            timestamps_seconds=...,
            current_time_index=...,    # Adapter 自己决定切片点
            sdc_track_index=...,
            frames=...,
            map_features=map_features,
            source=f"nuscenes:{scene_data['scene_token']}",
            ...
        )
```

### 4.4 关键难点

**难点 1：nuScenes 只有关键帧有 agent 标注**

Waymo 每帧（10Hz）都有完整标注。nuScenes 只在 2Hz 关键帧有标注。中间帧需要线性插值——但这不准确（车辆可能转弯）。对于 10Hz → 需要 4 倍插值。

**方案：** 不插值到 10Hz，改为接受 2Hz 的帧率。ScenarioBundle 的 `timestamps_seconds` 不假设固定帧率。引擎和算子中的"帧数"概念（如 `sustained: {frames: 3}`）在 2Hz 下语义不同——3 帧在 Waymo 是 0.3 秒，在 nuScenes 是 1.5 秒。**规则参数需要按数据源调整。** 或者用 `seconds` 替代 `frames`（`sustained: {seconds: 0.3}`），这在两个数据源下语义一致。

**难点 2：nuScenes 没有 traffic_light 的动态状态**

Waymo 每帧有 `dynamic_map_states`，包含每个 lane 的交通灯状态。nuScenes 的交通灯是独立的 `sample_annotation`，需要用空间关系（agent 位置 vs 交通灯位置）来判断。

**方案：** 在 NuScenesAdapter 中模拟 `TrafficLightState`——将 nuScenes 的交通灯标注转为与 Waymo 格式兼容的结构。但"红灯"的判断逻辑（`near_red_light_stop_point`）需要重新验证。

**难点 3：地图车道匹配**

Waymo 的地图 lane 用 polyline，lane_matching 算子做点到线段的投影。nuScenes 的 lane 是离散的图节点+边，没有连续的 polyline。

**方案：** 将 nuScenes lane 的左右边界展开为 polyline（取 lane 节点的中心线）。这对车道匹配足够了——`match_agent_to_lane` 只需要点到 polyline 的距离。但 lane 之间的拓扑关系（前驱/后继）丢失了。对于当前规则集（只用到"同车道"判断），不依赖拓扑，够用。如果未来规则需要"提前知道下一个 lane"（如预测车道变化），就需要拓扑信息。

---

## 5. 这个"假解耦"架构的诚实评价

### 5.1 做得好的地方

- **Rules DSL 层完全数据源无关。** YAML 规则不需要知道数据来自哪里
- **算子 Protocol 接口是真正的抽象。** `evaluate(context, frame, subject, args) → OperatorResult` 这个签名对任何数据源都适用
- **引擎核心（TriggerEngine / TemporalRuleEngine / EventPolicyEngine）基本不碰原始数据。** 只通过 AlignmentContext 和 TagTimeline 操作
- **ScenarioBundle 作为统一数据模型的思路是对的。** 只是当前填充逻辑全耦合在 WaymoAdapter 中

### 5.2 做得不够的地方

- **没有 Adapter 接口。** `WaymoScenarioAdapter` 是唯一的类，没有抽象。换数据源就是重写
- **SDC 概念硬编码太深。** `sdc_track_id` 散布在 engine/subjects/rules/operators 的 30+ 处。虽然不是大改动，但说明"自车"这个概念没有做统一的抽象
- **AgentState 字段被算子直接访问。** 这不是错误——Python 的鸭子类型天然支持——但意味着换数据源时，适配器必须精确复制所有字段名，没有编译期检查
- **地图模型太具体。** `MapFeature` 的 polyline/polygon 二分法对 Waymo 完美匹配，但对 lane graph 格式不够用
- **帧模型有几个隐式假设：** 10Hz 固定帧率、`current_time_index` 的切片方式、`phase` 的 history/current/future 三段式

### 5.3 如果一开始就为多数据源设计

会多做以下几件事：

1. **`BaseScenarioAdapter` 抽象类**，定义 `load() → ScenarioBundle` 接口
2. **`AgentState` 用 Protocol 而非具体 dataclass**——任何有 `center`/`velocity_x`/`heading`/`track_id`/`valid` 属性的对象都可以
3. **`EgoVehicle` 的概念单独抽象**，不叫 SDC，不和 track_index 绑定
4. **`MapFeature` 支持多种几何表示**（polyline / polygon / graph）
5. **帧模型参数化**：帧率、时间窗口大小、切片方式都可配置

但这些"多做一些"在当前只有一个数据源的情况下就是过度工程。**当前架构的简洁性恰恰来自于不做这些抽象。** 这是有意为之的务实选择。

---

## 6. 建议的渐进式解耦路径

如果确定要接入第二个数据源，建议分三步走：

### Phase 1：定义 Adapter 接口（最小侵入）

```python
# 新增文件: trigger_engine/data/base.py
class BaseScenarioAdapter(Protocol):
    """将外部数据格式转换为 ScenarioBundle"""
    def load(self, source: str | Path) -> ScenarioBundle: ...
    @property
    def source_type(self) -> str: ...
```

`WaymoScenarioAdapter` 实现这个接口。`NuScenesAdapter` 也实现。`run_review_batch.py` 根据文件扩展名或参数选择 adapter。

### Phase 2：泛化关键数据字段

```python
# AgentState: track_index 改为可选，track_id 改为 int | str
# ScenarioBundle: sdc_track_index 改为 ego_track_id（向后兼容别名）
# AlignmentContext: sdc_track_id → ego_track_id
```

### Phase 3：地图模型扩展（按需）

如果 nuScenes 的规则需要用到 lane 拓扑，再扩展 MapFeature。否则保持 polyline 方案。

---

## 7. 总结

| 问题 | 答案 |
|------|------|
| 接入第二数据源需要改多少代码？ | 约 650 行（新增 ~560 + 修改 ~90），占核心代码 10% |
| 最大的改动在哪？ | 新 Adapter（~300 行）+ 地图适配（~100 行） |
| 规则和算子需要改吗？ | 算子逻辑不改，但需确保适配器填充的 AgentState 字段名一致。YAML 规则可以不改 |
| SDC 硬编码是大问题吗？ | 不大。sdc 语义在 nuScenes 中一样适用（自车视角）。改 `sdc_` → `ego_` 约 30 处，纯搜索替换 |
| 架构是"假解耦"吗？ | 部分是的。Data/Alignment 层没有抽象接口，但 Engine/Rules/Policy 三层确实与数据源无关。整体上是一个"上层真解耦、下层单实现"的务实架构 |

**一句话：当前架构接入 nuScenes 的工作量在可控范围内（1-2 人周），最大的难题不是代码架构，而是两个数据集的语义差异——坐标系、帧率、地图格式、交通灯模型——这些是换任何架构都要解决的问题。**

---

*分析完成时间：2026-07-02 | 类型：架构冲击分析*
