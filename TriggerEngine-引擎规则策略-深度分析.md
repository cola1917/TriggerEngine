# TriggerEngine 三大核心模块深度分析：引擎 / 规则 / 策略

## 理解验证状态

| 核心概念 | 自我解释 | 理解"为什么" | 应用迁移 | 状态 |
|---------|---------|-------------|---------|------|
| YAML→AST→ExecutionPlan 编译链 | ✅ | ✅ | ✅ | 已理解 |
| RuleEngine 单帧评估循环 | ✅ | ✅ | ✅ | 已理解 |
| SubjectCache 候选对三级优化 | ✅ | ✅ | ✅ | 已理解 |
| 门控规则 (Gated Rule) 拓扑执行 | ✅ | ✅ | ⚠️ | 基本理解 |
| TagTimeline 时序匹配 | ✅ | ✅ | ✅ | 已理解 |
| TemporalRuleEngine (Sustained/Sequence) | ✅ | ✅ | ✅ | 已理解 |
| EventPolicy 四层管道 | ✅ | ✅ | ✅ | 已理解 |
| 三模块的协作关系 | ✅ | ✅ | ✅ | 已理解 |

---

## 模块全景：三者的角色与边界

```
┌─────────────────────────────────────────────────────────────────┐
│                        RULES (规则层)                            │
│  定义"检测什么"——把 YAML 文本变成可执行的数据结构                   │
│                                                                  │
│  YAML 文本 → RuleParser → RuleSet (AST)                          │
│                   ↓                                              │
│             RuleCompiler → ExecutionPlan                         │
│                             ├── single_frame_rules               │
│                             ├── temporal_rules                   │
│                             └── operator_names                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ ExecutionPlan
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       ENGINE (引擎层)                             │
│  执行"如何检测"——遍历帧、生成候选主体、运行算子、产出事件           │
│                                                                  │
│  TriggerEngine.evaluate(context)                                 │
│    ├── RuleEngine.evaluate()        ← 单帧规则，逐帧逐主体评估     │
│    │     └── SubjectCache            ← 候选对生成 + 缓存           │
│    ├── TagTimeline                   ← 存储已产生的标签事件        │
│    ├── TemporalRuleEngine.evaluate() ← 时序规则，基于标签做模式匹配 │
│    └── → TagEvent[] (原始事件流)                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ TagEvent[] (raw)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       POLICY (策略层)                             │
│  过滤噪音——冷却、压缩、合并、去重，从海量帧事件中提炼高价值信号      │
│                                                                  │
│  EventPolicyEngine.apply(events, rules)                          │
│    ├── Cooldown          ← 同 tag+subject N 帧内不重复            │
│    ├── Compact           ← 连续帧合并为区间                       │
│    ├── Episode           ← review 事件合并为剧集                  │
│    └── Review Dominance  ← 同家族高优先级覆盖低优先级              │
│    → TagEvent[] (最终审查事件)                                    │
└─────────────────────────────────────────────────────────────────┘
```

**一句话总结三者的分工：**

> Rules 是"菜谱"（定义检测什么），Engine 是"厨师"（执行检测过程），Policy 是"摆盘"（过滤和整理结果）。

---

## 1. RULES 层：从 YAML 文本到可执行计划

### 1.1 整体流程

```
YAML 文本 (str)
  │
  ▼ RuleParser.parse_yaml()
RuleSet (AST — 纯数据，未经验证)
  │
  ▼ RuleCompiler.compile()
ExecutionPlan (已验证 + 已分类)
```

### 1.2 AST 节点体系

```python
# —— 条件类型（规则的 when 子句）——
AllCondition(calls)              # 所有算子同时满足（AND）
SustainedTagCondition(tag, frames|seconds)  # 标签持续 N 帧/秒
SequenceTagCondition(steps, within_frames|seconds, max_gap)  # 标签序列

# —— 规则 ——
Rule(
    rule_id,                     # 唯一标识
    subject_type,                # "frame"|"agent"|"sdc_agent"|"lane"|"scenario"|"agent_pair"|"sdc_pair"
    condition,                   # 上述三种条件之一
    emit,                        # RuleEmit: tag_name + intent + metadata + policy
    kind,                        # "single_frame" | "temporal"
    window,                      # 可选的历史窗口限制
    pair,                        # PairConfig: "directed" | "unordered"
)

# —— 执行计划 ——
ExecutionPlan(
    plan_id,
    single_frame_rules,          # 直接评估数据的规则
    temporal_rules,              # 基于已有标签的规则
    operator_names,              # 引用的所有算子名（供验证）
)
```

**WHY 有两种条件（AllCondition vs Sustained/Sequence）但 AST 节点用 `|` 联合类型？**

单帧规则只能用 `AllCondition`——它直接对数据做判断。时序规则只能用 `SustainedTagCondition` 或 `SequenceTagCondition`——它们基于已有标签做时序匹配。虽然类型系统允许任意组合，但 `RuleCompiler` 在编译期做了严格校验，把不合法组合拦截在加载阶段。这样设计的目的是让 AST 保持简洁（3 个条件节点覆盖所有情况），而把类型约束放在 Compiler 中。

### 1.3 RuleParser：YAML → AST

解析器的核心是一个递归下降的结构化解析过程，入口是 `parse_yaml()`，然后按字段逐个解析：

```
parse_yaml(text)
  → yaml.safe_load(text)
  → for each rule in doc["rules"]:
      _parse_rule(raw, index)
        ├── 解析 id, subject, kind, description
        ├── _parse_temporal_condition(when)  或  _parse_all_condition(when["all"])
        ├── 解析 emit (tag, value, metadata, intent)
        ├── _parse_policy(emit) → EventPolicy
        └── _parse_pair(raw) → PairConfig
```

**设计要点：**

- **每个字段都有存在性+类型校验。** 例如 `kind` 必须是 `"single_frame"` 或 `"temporal"`，`subject` 必须在 7 种合法值中
- **报错信息包含规则索引。** 如 `rules[3].when.sustained.frames must be a positive integer`——这让用户能快速定位 YAML 中哪条规则有问题
- **双模式时间窗口互斥。** `sustained` 不能同时有 `frames` 和 `seconds`；`sequence` 不能同时有 `within_frames` 和 `within_seconds`。Parser 层面就拦截了这种歧义

**时序条件的解析逻辑：**

```python
def _parse_temporal_condition(self, when_raw, rule_index):
    # 关键判断：时序规则不能有 when.all（它们不直接调算子）
    if "all" in when_raw:
        raise RuleParseError("temporal rule must not contain 'when.all'")

    # 两条路径：
    if "sequence" in when_raw:
        return self._parse_sequence_condition(when_raw, rule_index)
    # 否则就是 sustained
    tag_name = when_raw.get("tag")       # 引用已有标签
    sustained_raw = when_raw.get("sustained")
    frames = sustained_raw.get("frames")  # 或 seconds
    return SustainedTagCondition(tag_name, frames=frames)
```

**WHY 时序规则引用的是"标签名"而非"规则 ID"？**

标签名是语义层面的（如 `low_ttc_pair`），规则 ID 是实现层面的（如 `rule_042`）。标签名让规则 DSL 更具可读性——你看到 `sustained: {frames: 3}` 就知道"让 `low_ttc_pair` 这个标签持续 3 帧"。Compiler 在编译期把标签名映射回规则（通过 `single_frame_emit_tags` 字典），如果标签不存在就报错。

### 1.4 RuleCompiler：AST → ExecutionPlan

编译器做了三件事：**分类、验证、收集元数据**。

```
compile(plan_id, rule_set, operator_registry):
  for each rule:
    if rule.kind == "single_frame":
        ├── 验证 condition 是 AllCondition
        ├── 验证每个 operator 在 registry 中存在
        ├── 验证 subject_type 兼容 (sdc_agent→agent, sdc_pair→agent_pair)
        ├── 验证 result_kind == "predicate"
        ├── 收集 operator_names
        └── 记录 emit.tag_name → subject_type 映射

    elif rule.kind == "temporal":
        ├── 验证引用的 tag 在 single_frame 中有定义
        ├── 验证 subject_type 匹配
        └── 验证参数合法性 (frames > 0, steps ≥ 2 等)

  return ExecutionPlan(
      single_frame_rules,   # 已验证的单帧规则
      temporal_rules,       # 已验证的时序规则
      operator_names,       # 所有引用的算子
  )
```

**编译期的核心约束：**

| 检查项 | 位置 | 错误时的后果 |
|--------|------|-------------|
| 算子是否存在 | `operator_registry.get()` | 运行时 NameError，编译期就能发现 |
| subject_type 兼容 | `op.subject_type == compatible_type` | 算子接收 agent 但规则是 sdc_pair → 不匹配 |
| result_kind 正确 | `op.result_kind == "predicate"` | 把计算型算子当谓词用 → 逻辑错误 |
| 时序标签引用 | `tag in single_frame_emit_tags` | 引用不存在的标签 → 运行时永远不触发 |
| 序列长度 ≥ 2 | `len(steps) >= 2` | 单步序列等于单帧规则，语义错误 |

### 1.5 RuleRegistry：规则包管理

```python
class RuleRegistry:
    def register_yaml(self, name, yaml_text):
        rule_set = RuleParser().parse_yaml(yaml_text)   # 解析
        plan = RuleCompiler().compile(name, rule_set, ...)  # 编译
        self._plans[plan.plan_id] = plan                 # 存储
        return plan

    def activate(self, plan_id):   # 切换当前使用的规则包
        self._active_plan_id = plan_id

    def active_plan(self):          # 获取当前规则包
        return self._plans[self._active_plan_id]
```

**WHY 支持多个 plan 但只有一个 active？**

允许注册多个规则包（如 `classic_v1`、`experimental_v2`），但同一时刻只有一个生效。这支持了规则包的版本管理和 A/B 对比：同一批数据可以用不同规则包跑两次，比较结果差异。

---

## 2. ENGINE 层：执行检测的核心管道

### 2.1 整体架构

```
TriggerEngine.evaluate(context)
  │
  ├── [阶段 1] 分离门控/非门控单帧规则
  │     _gated_rules(plan) → GatedRule[]
  │
  ├── [阶段 2] 第一轮：非门控单帧规则
  │     RuleEngine.evaluate(ungated_rules)
  │     → single_events + TagTimeline
  │
  ├── [阶段 3] 迭代轮：门控单帧规则（拓扑执行）
  │     while pending:
  │       for each gated rule:
  │         if 所有前置标签已完成:
  │           RuleEngine.evaluate(gated_rule, subject_id_filters)
  │           → 追加到 single_events
  │
  ├── [阶段 4] 时序规则
  │     TemporalRuleEngine.evaluate(temporal_rules, timeline)
  │     → temporal_events
  │
  └── [阶段 5] 事件策略
        EventPolicyEngine.apply(all_events, all_rules)
        → 最终事件
```

### 2.2 RuleEngine：单帧规则的核心评估循环

这是整个引擎中最"热"的代码路径——每条单帧规则、每帧、每个主体都要经过这个循环。

```python
class RuleEngine:
    def evaluate(self, rule_set, context, subject_cache, subject_id_filters, profile):
        events = []

        for rule in rule_set.rules:
            for aligned_frame in context.input_frames:        # 遍历帧
                if not _rule_applies_to_frame(rule, aligned_frame):
                    continue  # 跳过不适用帧（如 only_current_frame 约束）

                # 获取该帧该规则的主体列表（关键：这里走 SubjectCache）
                subjects = subject_cache.subjects_for_rule(
                    rule, aligned_frame, context=context,
                    allowed_subject_ids=allowed_subject_ids)

                for subject in subjects:                      # 遍历主体
                    # SDC 过滤
                    if rule.subject_type == "sdc_agent":
                        if subject.track_id != context.sdc_track_id:
                            continue
                    elif rule.subject_type == "sdc_pair":
                        if subject.ego.track_id != context.sdc_track_id:
                            continue

                    # 核心：逐个算子评估（短路求值）
                    all_true = True
                    for call in rule.condition.calls:
                        operator = self._registry.get(call.operator_name)
                        result = operator.evaluate(
                            context=context, frame=aligned_frame,
                            subject=subject, args=call.args)
                        # 谓词算子必须返回 bool
                        if not result.value:
                            all_true = False
                            break  # AND 语义，第一个 False 就退出

                    if all_true:
                        events.append(TagEvent(
                            tag_name=rule.emit.tag_name,
                            subject_type=rule.subject_type,
                            subject_id=subject_id,
                            ...
                        ))
        return tuple(events)
```

**三件事值得深入讲：**

#### 2.2.1 短路求值 (Short-circuit Evaluation)

```python
for call in rule.condition.calls:
    result = operator.evaluate(...)
    if not result.value:
        all_true = False
        break   # ← 后面的算子不执行了
```

条件是 AND 语义（`AllCondition`），一旦某个算子返回 False，后续算子全部跳过。**顺序至关重要**——规则定义者应该把"最便宜、最可能失败"的算子放在 YAML 最前面。

例如 `low_ttc_pair` 规则：

```yaml
when:
  all:
    - operator: predicate.pair_types_are    # 第1: 类型检查（极快，O(1)）
      args: {ego_type: vehicle, other_type: vehicle}
    - operator: predicate.pair_ego_speed_above  # 第2: 速度检查（快）
    - operator: predicate.pair_in_front     # 第3: 空间位置（快）
    - operator: predicate.low_ttc           # 第4: TTC 计算（中等）
    - operator: predicate.same_lane_or_path # 第5: 车道匹配（最贵！）
```

WHY 把车道匹配放最后？它涉及地图查询 + 航向比对，是最昂贵的算子。前面的检查能过滤掉 90%+ 的候选对，只有极少数能走到第 5 步。

#### 2.2.2 `_rule_applies_to_frame` 帧级过滤

```python
def _rule_applies_to_frame(rule, aligned_frame):
    for call in rule.condition.calls:
        if call.args.get("only_current_frame", False):
            return (aligned_frame.visibility == "current"
                    and aligned_frame.frame.phase == "current")
    return True  # 默认：所有 input_frames
```

某些规则（如 `sdc_blocked_unable_to_proceed`）只需要评估当前帧，不需要看历史帧。`only_current_frame: true` 参数让它们在历史帧上直接跳过，节省大量计算。

#### 2.2.3 SDC 主体过滤

```python
if rule.subject_type == "sdc_agent":
    if subject.track_id != context.sdc_track_id:
        continue  # 不是 SDC，跳过
```

对于 `sdc_agent` 类型，虽然 `_get_subjects` 返回了所有 agent，但引擎层只保留 SDC 自己。**WHY 不在 SubjectCache 层过滤？** 因为 SubjectCache 是通用的——同一帧的 agent 列表被所有规则共享。如果 SubjectCache 按 SDC 过滤，非 SDC 的 agent 规则就拿不到数据了。过滤放在 RuleEngine 的评估循环中是正确的位置——每条规则根据自己的 subject_type 决定保留哪些主体。

### 2.3 SubjectCache：候选对的三级优化策略

这是整个引擎的性能核心。`SubjectCache` 为 `agent_pair` / `sdc_pair` 规则生成候选主体对时，有三条路径：

```
┌─────────────────────────────────────────────────────────────┐
│            SubjectCache.subjects_for_rule()                   │
│                                                              │
│  if rule.subject_type 不是 pair 类型:                         │
│    → 直接返回缓存的普通主体列表（无优化）                       │
│                                                              │
│  if plan.can_prune == False:                                 │
│    → 返回全量对（无优化，O(n²)）                               │
│                                                              │
│  if rule.subject_type == "sdc_pair":                         │
│    ├── [门控] SDC 急刹车运动学检查                             │
│    │   if 不满足: return []  ← 整条规则跳过!                   │
│    ├── [路径A] SDC 标量模式 O(n)                              │
│    │   对每个 other: 欧氏距离预过滤 → plan.matches()           │
│    └── [路径B] sdc_track_id 不存在时的退化                     │
│                                                              │
│  elif PairGeometryCache.should_vectorize(len(agents), plan):  │
│    └── [路径C] NumPy 向量化 O(n²) 但常数极小                   │
│        PairGeometryCache(agents).candidate_index_pairs(plan)  │
│                                                              │
│  else:                                                       │
│    └── [路径D] 通用标量 O(n²) + 欧氏距离预过滤                  │
└─────────────────────────────────────────────────────────────┘
```

#### 2.3.1 PairCandidatePlan 和 PairCandidatePredicate

这两个类是候选对筛选的"配置层"：

```python
@dataclass(frozen=True)
class PairCandidatePredicate:
    operator_name: str         # 如 "predicate.low_ttc"
    args: dict[str, object]    # 如 {"max_lateral_m": 2.0, ...}

    @property
    def search_radius_m(self) -> float | None:
        # 从参数中提取最大空间范围
        # 例如 low_ttc: sqrt(4² + 40²) ≈ 40.2m
        #      vru_close: 直接返回 max_distance_m = 15.0m

    def matches(self, ego, other) -> bool:
        # 快速空间筛选：将 other 转到 ego 坐标系，检查是否在参数范围内
        # 这是算子的"廉价近似版"——只做空间判断，不做完整逻辑
```

**关键设计：`matches()` 是算子的"廉价代理"**

真实的算子（如 `predicate.low_ttc`）会做完整的 TTC 计算 + 车道匹配。`PairCandidatePredicate.matches()` 只做纯几何的空间范围检查——它在还没创建 `AgentPairSubject` 之前就能快速排除不满足空间约束的对。

```python
def build_pair_candidate_plan(rule):
    # 从规则的 AllCondition 中提取所有"可做空间筛选"的谓词
    predicates = []
    for call in rule.condition.calls:
        predicate = _candidate_predicate_for(call.operator_name, call.args)
        if predicate is not None:  # 只有空间类谓词才加入
            predicates.append(predicate)
    return PairCandidatePlan(rule.rule_id, tuple(predicates))
```

`_candidate_predicate_for` 只识别 9 种空间谓词：

```python
# 能被候选对筛选利用的谓词（白名单）
"predicate.close_lateral_gap"
"predicate.lateral_gap_between"
"predicate.same_path_overlap"
"predicate.pair_in_front"
"predicate.low_ttc"
"predicate.pair_ego_hard_braking"
"predicate.vru_close_interaction"
"predicate.sdc_blocked_unable_to_proceed"
"predicate.sdc_lane_change_conflict"
```

其他算子（如 `predicate.pair_types_are`、`predicate.pair_ego_speed_above`）不涉及空间判断，不在候选对筛选层处理。

#### 2.3.2 SDC 急刹车运动学门控

这是最近提交的优化（commit `5fe3f6b` Gate hard braking pair candidates）：

```python
if (rule.subject_type == "sdc_pair"
    and _has_pair_ego_hard_braking_predicate(plan)
    and not _sdc_hard_braking_gate_passes(context, aligned_frame, ...)):
    # SDC 当前没有急刹车 → 整条规则返回空候选对！
    self._rule_cache[key] = []
    return []
```

**WHY 这是最有效的优化之一？**

`sdc_hard_braking` 规则的触发条件之一是 SDC 在 1 秒窗口内减速度 ≤ -3m/s²、速度下降 ≥ 2m/s。对于绝大多数帧，SDC 正常行驶时这个条件不成立。与其生成所有候选对然后逐个算子评估（最后发现刹车条件不满足），不如在最外层先检查 SDC 自己是否在急刹车——如果不满足，整条规则直接跳过。

这相当于把"最不可能通过的条件"提到了候选对生成之前。效果：免去了对每帧、每个 other agent 进行欧氏距离计算和 predicate 匹配的开销。

#### 2.3.3 NumPy 向量化策略

```python
class PairGeometryCache:
    MIN_VECTOR_AGENT_COUNT = 32  # 阈值：agent 数 ≥ 32 才启用

    def __init__(self, agents):
        # 一次性构建全局矩阵
        self._xs = np.array([a.center.x for a in agents])       # (N,)
        self._ys = np.array([a.center.y for a in agents])       # (N,)
        self._cos = np.cos(headings)                            # (N,)
        self._sin = np.sin(headings)                            # (N,)

    def _relative_lon_lat(self):
        # 用广播计算所有对的相对位置
        dx = self._xs[None, :] - self._xs[:, None]   # (N, N)
        dy = self._ys[None, :] - self._ys[:, None]   # (N, N)
        # 旋转到 ego 坐标系
        self._lon = dx * self._cos[:, None] + dy * self._sin[:, None]
        self._lat = -dx * self._sin[:, None] + dy * self._cos[:, None]
        # 结果：lon[i, j] = agent_j 在 agent_i 坐标系中的纵向距离

    def candidate_index_pairs(self, plan):
        # 对每个谓词构建布尔掩码，用 & 组合
        mask = ~np.eye(count, dtype=bool)      # 排除自对 (i,i)
        for predicate in plan.predicates:
            mask &= (条件判断)                   # 批量筛选
        # np.nonzero(mask) → 返回所有 True 位置的索引
        ego_indices, other_indices = np.nonzero(mask)
        return [(int(i), int(j)) for i, j in zip(ego_indices, other_indices)]
```

**WHY 阈值是 32？**

- NumPy 的优势在于批量操作——一旦构建了 (N, N) 矩阵，所有谓词筛选都是向量化的
- 但构建矩阵本身有 Python→C 的数据拷贝开销
- 32 是经验值：低于此数时，标量循环（含欧氏距离预过滤）的总开销 < NumPy 的拷贝+广播开销
- 当 agent=50 时，NumPy 版本通常比标量快 3-5 倍

**缓存机制：** `_lon` 和 `_lat` 矩阵只计算一次（惰性求值），多个规则可以复用同一个 `PairGeometryCache` 实例。

#### 2.3.4 缓存键设计

```python
# 通用主体缓存键：场景 + 帧 + 主体类型
def _key(aligned_frame, subject_type):
    return (scenario_id, step_index, subject_type)

# 规则级缓存键：场景 + 规则 + 帧 + 主体类型
def _rule_key(aligned_frame, rule_id, subject_type):
    return (scenario_id, rule_id, step_index, subject_type)
```

**WHY 有两级缓存？**

- 通用缓存 (`_cache`)：同帧同主体类型被多条规则共享。例如 5 条 `sdc_agent` 规则评估同一帧，agent 列表只构建一次
- 规则级缓存 (`_rule_cache`)：pair 规则需要根据 `PairCandidatePlan` 生成筛选后的候选对——不同规则有不同筛选条件，所以需要按 rule_id 分开缓存

### 2.4 TagTimeline：标签时间线

这是时序规则的"数据库"——存储所有单帧规则产生的事件，提供高效查询。

```python
class TagTimeline:
    def __init__(self):
        self._data: dict[(tag, type, id, frame), bool]         # 存在性查询 O(1)
        self._events: dict[(tag, type, id, frame), TagEvent]   # 事件内容查询 O(1)
        self._timestamps: dict[frame, float]                   # 帧→时间戳映射
        self._subject_frames: dict[(tag, type, id), set[frame]] # 主体→帧集合
        self._tag_subjects: dict[(tag, type), set[id]]          # 标签→主体集合
```

**四层索引，各司其职：**

| 索引 | 键 | 值 | 用途 |
|------|----|----|------|
| `_data` | (tag, type, id, frame) | bool | `has_at(key, frame)` — "帧 X 有标签 Y 吗？" |
| `_events` | (tag, type, id, frame) | TagEvent | `event_at(key, frame)` — 获取完整事件 |
| `_subject_frames` | (tag, type, id) | {frame} | `frames_for(key)` — "主体在哪些帧有这个标签？" |
| `_tag_subjects` | (tag, type) | {id} | `subject_ids_for(tag, type)` — "哪些主体有这个标签？" |

**WHY 用 4 个字典而非 1 个？**

每个字典服务于不同的查询模式。如果只有一个 `(tag, type, id, frame) → TagEvent` 字典：
- 查"某帧是否有某标签"：可以做，但需要取整个事件再判断
- 查"某主体在哪些帧有标签"：需要遍历所有 key，O(total_events)
- 查"哪些主体有某标签"：同上

分开索引后，每种查询都是 O(1) 或 O(该主体的帧数)。

**Sustained 查询的核心逻辑：**

```python
def sustained(self, key, end_frame_index, frames):
    # 检查 [end - frames + 1, end] 窗口内是否每帧都有事件
    for i in range(end_frame_index - frames + 1, end_frame_index + 1):
        if not self.has_at(key, i):    # O(1) 哈希查询
            return False, ()
    return True, tuple(supporting)
```

**Sequence 查询的核心逻辑：**

```python
def sequence(self, keys, end_frame_index, within_frames):
    # 在 [end - within + 1, end] 窗口内，按顺序找 keys 中的每个标签
    next_search_start = start_frame_index
    for key in keys:
        for frame_index in range(next_search_start, end_frame_index + 1):
            if self.has_at(key, frame_index):
                matched_frame = frame_index
                break
        if matched_frame is None:
            return False, ()
        supporting.append(matched_frame)
        next_search_start = matched_frame  # 允许同帧匹配
    return True, tuple(supporting)
```

**WHY `next_search_start = matched_frame`（允许同帧匹配）而非 `matched_frame + 1`（严格递增）？**

实践中，序列中的多个标签可能在同帧触发。例如 `cut_in_lateral_approach` 和 `same_path_overlap` 可能同时检测到——如果要求严格递增，序列就会失败。非递减语义更贴合实际数据特征。

### 2.5 TemporalRuleEngine：时序规则执行

```python
class TemporalRuleEngine:
    def evaluate(self, rules, context, timeline, subject_cache, profile):
        for rule in rules:
            if isinstance(rule.condition, SustainedTagCondition):
                events.extend(self._evaluate_sustained(rule, ...))
            elif isinstance(rule.condition, SequenceTagCondition):
                events.extend(self._evaluate_sequence(rule, ...))
```

#### Sustained 评估

```
_evaluate_sustained(rule):
  for each subject_id that has the source tag:
    for each frame where the subject has the source tag:
      get aligned_frame for that frame
      check sustained(seconds|frames) on timeline
      if ok: emit temporal event with supporting frame info
```

本质上是在问："对于某个 subject，源标签在某个帧附近持续出现了足够久吗？"

#### Sequence 评估

```
_evaluate_sequence(rule):
  收集所有源标签的 subject_id 交集（三步序列，三步都必须触发过的 subject 才考虑）
  for each candidate subject_id:
    从最后一个标签的触发帧开始反向查找
    check sequence(keys, end_frame, within_frames|seconds) on timeline
    if ok: emit temporal event
```

**关键优化：subject_id 交集**

```python
candidate_subject_ids = None
for tag_name in source_tags:
    ids = set(timeline.subject_ids_for(tag_name, rule.subject_type))
    candidate_subject_ids = (
        ids if candidate_subject_ids is None
        else candidate_subject_ids & ids  # ← 交集
    )
```

对于三步序列 `adjacent_vehicle → cut_in_lateral_approach → same_path_overlap`：
- 如果 subject "3:7" 只触发了 `adjacent_vehicle` 但没触发 `cut_in_lateral_approach`
- 那它永远不可能完成完整序列
- 提前排除掉，避免无谓的 timeline 查询

### 2.6 Gated Rules：门控规则的拓扑执行

这是 `TriggerEngine._gated_rules()` 和评估循环中最精妙的部分。

#### 问题背景

考虑 cut-in 序列规则：

```yaml
# 时序规则引用了三步标签
- id: cut_in_confirmed
  when:
    sequence:
      - tag: adjacent_vehicle        # 步骤 1
      - tag: cut_in_lateral_approach # 步骤 2
      - tag: same_path_overlap       # 步骤 3
```

这三个标签分别由三条单帧规则产生。如果场景中没有触发 `adjacent_vehicle`，那 `cut_in_lateral_approach` 和 `same_path_overlap` 的评估就毫无意义——序列第一步就不可能完成。**门控机制正是利用这个依赖关系来跳过不必要的单帧规则评估。**

#### 门控的构建

```python
def _gated_rules(self, plan):
    # 1. 收集时序规则中引用的标签名
    # 2. 对于 SequenceTagCondition 且 subject_type 是 pair 类型的：
    #    - 序列第一步 → sequence_first_tags（不需要门控，但作为"入口"）
    #    - 序列后续步骤 → predecessor_tags_by_tag[steps[i]] = {steps[i-1]}
    # 3. 排除同时是 sustained 源的标签（sustained 不参与序列门控）
    # 4. 返回 GatedRule(rule, predecessor_tags)

    # 例如:
    # cut_in_lateral_approach 的 predecessor_tags = {"adjacent_vehicle"}
    # same_path_overlap 的 predecessor_tags = {"cut_in_lateral_approach"}
```

#### 迭代执行

```
第 1 轮: 执行所有非门控规则（包括序列第一步 adjacent_vehicle）
  → 产出 adjacent_vehicle 事件
  → completed_tags = {adjacent_vehicle, ...}

第 2 轮: 检查 pending 中的门控规则
  cut_in_lateral_approach: 前置标签 adjacent_vehicle 已完成 ✓
    → 执行，但只评估 subject_ids 在 adjacent_vehicle 事件中出现过的那些对
    → completed_tags 增加 cut_in_lateral_approach

第 3 轮:
  same_path_overlap: 前置标签 cut_in_lateral_approach 已完成 ✓
    → 执行，同上过滤
    → completed_tags 增加 same_path_overlap

第 4 轮: pending 为空，循环结束
```

**门控的两种优化效果：**

1. **跳过不必要的规则评估：** 如果场景中根本没有 `adjacent_vehicle` 事件，`cut_in_lateral_approach` 和 `same_path_overlap` 两条规则完全不会被评估
2. **缩小评估范围：** 即使评估，也只评估那些"前置标签触发过的 subject_ids"，候选对数量大幅减少

**防御性回退：**

```python
if not progressed:
    # 存在依赖环或其他异常 → 不做门控，一次性评估所有剩余规则
    fallback_events = self._rule_engine.evaluate(
        RuleSet(rules=fallback_rules), context, ...)
    break
```

这是"正确性优先于性能"的体现——理论上不应该出现依赖环（Compiler 验证了标签引用），但万一有，fallback 保证不会漏掉事件。

---

## 3. POLICY 层：事件后处理管道

### 3.1 为什么需要 Policy 层

单帧规则直接产出的原始事件量是巨大的。以 9 秒场景（91 帧，10Hz）为例：
- 如果 SDC 停在红灯前 30 帧，`sdc_vehicle_stopped_at_red` 会触发 30 次——但分析师只需要知道"SDC 在红灯前停了"
- 如果同一个切入行为同时满足 `cut_in_confirmed` 和 `cut_in_risk`，两者都输出就冗余了

Policy 层的任务就是把这些"帧级信号"整理成"场景级事件"。

### 3.2 四层管道

```
EventPolicyEngine.apply(events, rules)
  │
  ├── [层 1] Cooldown 冷却
  │     同 tag + 同 subject 在 N 帧内只保留第一次
  │
  ├── [层 2] Compact 压缩
  │     同一 subject 的连续帧事件合并为一个区间事件
  │
  ├── [层 3] Episode 剧集
  │     review 意图的事件合并为 episode，
  │     附带 supporting_frames（支持性帧的索引和时间戳）
  │
  └── [层 4] Review Dominance 审查去重
        同一 review_family + 同一 subject，
        高优先级 episode 覆盖低优先级
```

### 3.3 Cooldown：时间冷却

```python
def apply(self, events, rules):
    cooldown_by_tag = {}  # 从 rules 中收集每个 tag 的 cooldown_frames
    suppressed_until = {}  # (scenario, tag, type, id) → 下次允许输出的帧号

    for event in events:
        key = (event.scenario_id, event.tag_name, event.subject_type, event.subject_id)
        cooldown = cooldown_by_tag.get(event.tag_name, 0)

        if cooldown <= 0:
            result.append(event)
            continue

        last = suppressed_until.get(key, -1)
        if event.frame_index <= last:
            continue  # 还在冷却期，丢弃

        suppressed_until[key] = event.frame_index + cooldown
        result.append(event)  # 保留，并记录冷却期
```

**示例：**

```
sdc_hard_braking, cooldown_frames=20
帧 11: 触发 → 保留, suppressed_until = 31
帧 12: 触发 → 丢弃 (12 ≤ 31)
帧 13: 触发 → 丢弃
...
帧 32: 触发 → 保留, suppressed_until = 52
```

**WHY 用帧数而非秒数？**
帧数是确定的——数据是 10Hz 固定帧率。用帧数可以精确定义"间隔多少帧"。如果用秒数，会因为浮点精度引入边界问题。

### 3.4 Compact：连续帧压缩

```python
def _compact_events(events, rules):
    # 1. 识别有 compact 策略的 tag
    # 2. 对 compactable 事件按 (scenario, source, tag, rule, type, id, frame) 排序
    # 3. 遍历：如果当前事件和 pending 是同一 group 且帧号连续 → 合并
    #    否则 → flush pending，开始新的 pending
    # 4. 合并后的事件包含：
    #    - start_frame_index / end_frame_index（区间范围）
    #    - frame_count（包含的帧数）
    #    - raw_frame_indices（原始帧号列表）
```

**核心逻辑：**

```python
for event in compactable:
    group_key = (scenario, source, tag, rule, type, subject_id)
    prev_key = (...) if pending else None

    if pending and group_key == prev_key and event.frame_index == pending_indices[-1] + 1:
        # 同一 group，且帧号连续 → 合并
        pending_indices.append(event.frame_index)
    else:
        # 不同 group 或不连续 → flush 再开始新的
        _flush()
        pending = event
        pending_indices = [event.frame_index]
```

**WHY 只在 `intent != "review"` 时才压缩？**

压缩是针对 `debug` 和 `supporting` 意图的中间标签。review 级别的事件走的是 Episode（下一层），那是一种更"高级"的合并方式——包含 supporting frames 信息。两种合并面向不同用途，互斥。

### 3.5 Episode：审查剧集合并

```python
def _episode_events(events, rules):
    # 只处理 intent="review" 且有 episode policy 的事件
    # 逻辑和 compact 类似（连续帧合并），但额外处理：
    #   - supporting_frame_indices: 合并所有 supporting frames
    #   - event_count: episode 包含的原始事件数
    #   - raw_event_frame_indices / raw_event_timestamps_seconds
```

**WHY Episode 和 Compact 逻辑相似但分开实现？**

| | Compact | Episode |
|------|---------|---------|
| 适用意图 | debug, supporting | review |
| 合并内容 | 只有帧范围 | 帧范围 + supporting frames + 元数据 |
| 语义 | "这个信号持续了一段时间" | "这是一个需要审查的事件剧集" |
| 输出 | 压缩后的中间信号 | 最终审查事件 |

两者面向不同的消费者：Compact 输出给后续的时序规则做输入；Episode 输出给人类分析师在 viewer 中查看。

### 3.6 Review Dominance：审查优先级去重

```python
def _review_dominance(events):
    # 1. 按 review_family 分组（同一家族的事件，如 cut_in）
    # 2. 每组中找到最高优先级的 episode
    # 3. 低优先级 episode 如果和高优先级的区间重叠 → 丢弃
    # 4. 非重叠的低优先级 episode 保留
```

**示例：cut_in 家族**

```
cut_in_risk       (priority=20, 帧 40-45)
cut_in_confirmed  (priority=10, 帧 42-48)

重叠区间: 帧 42-45 重叠
结果: cut_in_confirmed 被丢弃（它的整个区间 42-48 与 cut_in_risk 的 40-45 重叠）
```

**但这里有个微妙的地方：**

```python
if e_start <= best_end and e_end >= best_start:
    continue  # 重叠 → 丢弃
```

这是**区间重叠判断**，不是包含判断。只要低优先级事件和高优先级事件有任何帧重叠，低优先级的就被丢弃。这比"完全包含"更激进——但也更安全，避免向分析师展示"几乎重复"的事件。

**WHY 在全部事件上做 Dominance 而非只在同一 subject 内？**

`_dominance_key` 包含了 `subject_id`：

```python
def _dominance_key(e):
    return (scenario_id, source, subject_type, str(subject_id),
            metadata.get("review_family"))
```

所以实际上是在 **"同一场景 + 同一主体类型 + 同一 subject + 同一家族"** 内做优先级比较。不同 subject 之间不会相互影响——这是正确的，因为 car A 的切入行为和 car B 的切入行为是独立的事件。

---

## 4. 三模块协作全景：完整执行追踪

用一个具体场景把三模块串联起来：**检测一次 cut-in（其他车辆切入 SDC 前方）**。

```
═══════════════════════════════════════════════════════════════
阶段 0: 规则加载 (RULES 层)
═══════════════════════════════════════════════════════════════

1. YAML 文本 → RuleParser.parse_yaml()
   产出: RuleSet(rules=[
     Rule(id="adjacent_vehicle", kind="single_frame", subject="sdc_pair",
          condition=AllCondition([pair_types_are, lateral_gap_between])),
     Rule(id="cut_in_lateral_approach", kind="single_frame", subject="sdc_pair",
          condition=AllCondition([pair_types_are, pair_ego_speed_above, ...])),
     Rule(id="same_path_overlap", kind="single_frame", subject="sdc_pair",
          condition=AllCondition([pair_types_are, same_path_overlap])),
     Rule(id="cut_in_confirmed", kind="temporal", subject="sdc_pair",
          condition=SequenceTagCondition(steps=[
              adjacent_vehicle, cut_in_lateral_approach, same_path_overlap
          ], within_frames=8)),
     ...
   ])

2. RuleSet → RuleCompiler.compile()
   产出: ExecutionPlan(
     single_frame_rules=[adjacent_vehicle, cut_in_lateral_approach,
                         same_path_overlap, ...],
     temporal_rules=[cut_in_confirmed, ...],
     operator_names=["predicate.pair_types_are", "predicate.lateral_gap_between", ...]
   )

3. rule_registry.activate("classic_v1")

═══════════════════════════════════════════════════════════════
阶段 1: 引擎评估 — 非门控单帧规则 (ENGINE 层)
═══════════════════════════════════════════════════════════════

4. TriggerEngine.evaluate(context)
   context 包含 11 帧输入（帧 1-10 历史 + 帧 11 当前）

5. _gated_rules(plan) 分析:
   - adjacent_vehicle 是序列第一步 → 非门控
   - cut_in_lateral_approach 有前置标签 adjacent_vehicle → 门控
   - same_path_overlap 有前置标签 cut_in_lateral_approach → 门控
   → ungated_rules 包含 adjacent_vehicle 和其他非序列规则

6. RuleEngine.evaluate(ungated_rules) 第 1 轮:

   遍历帧 1-11:
     帧 7: adjacent_vehicle 规则
       SubjectCache.subjects_for_rule("adjacent_vehicle", frame_7)
         → SDC 是 agent 103, 有 25 个其他 agent
         → SDC 搜索半径 18m: 欧氏距离过滤后剩 8 个候选
         → plan.matches(): lateral_gap_between 检查
         → 4 个通过 → 4 个 AgentPairSubject

       遍历这 4 个 subject:
         subject "103:207" (agent 207 在 SDC 左前方):
           pair_types_are(vehicle, vehicle) → True
           lateral_gap_between(min_lat=1.5, max_lat=4.5, max_lon=15) → True
           → 触发! TagEvent(tag="adjacent_vehicle", subject_id="103:207", frame=7)

       其他 3 个 subject 未通过 → 不触发

   所有非门控规则评估完毕
   → TagTimeline.from_events(): 构建时间线索引

═══════════════════════════════════════════════════════════════
阶段 2: 引擎评估 — 门控单帧规则 (ENGINE 层)
═══════════════════════════════════════════════════════════════

7. pending = [GatedRule(cut_in_lateral_approach, ["adjacent_vehicle"]),
              GatedRule(same_path_overlap, ["cut_in_lateral_approach"])]

   第 2 轮:
     cut_in_lateral_approach: 前置 "adjacent_vehicle" 已完成 ✓
       → 只评估 subject_ids = {"103:207"}（从 adjacent_vehicle 事件中提取）
       → RuleEngine.evaluate(..., subject_id_filters={"103:207"})
       → 帧 7: agent pair "103:207"
           pair_ego_speed_above(0.5) → SDC 速度 8.2m/s → True
           lateral_gap_between(1.0-4.5m, 15m) → True
           lateral_motion_toward(0.2m/s) → True
           heading_converging(0.0-0.7rad) → True
           → 触发! TagEvent(tag="cut_in_lateral_approach", subject_id="103:207", frame=7)
       → completed_tags 增加 "cut_in_lateral_approach"

   第 3 轮:
     same_path_overlap: 前置 "cut_in_lateral_approach" 已完成 ✓
       → 只评估 subject_ids = {"103:207"}
       → 帧 9: agent pair "103:207" 现在在 SDC 正前方 3m
           same_path_overlap(max_lat=1.2, lon=0-20m) → True
           → 触发! TagEvent(tag="same_path_overlap", subject_id="103:207", frame=9)

═══════════════════════════════════════════════════════════════
阶段 3: 时序规则 (ENGINE 层)
═══════════════════════════════════════════════════════════════

8. TemporalRuleEngine.evaluate(temporal_rules, timeline):

   cut_in_confirmed 规则:
     source_tags = [adjacent_vehicle, cut_in_lateral_approach, same_path_overlap]
     候选 subject_ids = 三个标签都触发的 subject 的交集
     → {103:207} ✓

     for subject_id "103:207":
       last_tag = "same_path_overlap" → 帧 9
       timeline.sequence(
         keys=[adjacent_vehicle(103:207),
               cut_in_lateral_approach(103:207),
               same_path_overlap(103:207)],
         end_frame=9, within_frames=8
       ):
         搜索窗口: 帧 [2, 9]
         adjacent_vehicle: 在帧 7 ✓
         cut_in_lateral_approach: 从帧 7 开始搜, 帧 7 ✓
         same_path_overlap: 从帧 7 开始搜, 帧 9 ✓
       → 序列完成! within_frames 检查: 9 - 7 + 1 = 3 ≤ 8 ✓

       → TagEvent(
           tag="cut_in_confirmed",
           subject_id="103:207",
           frame=9,
           metadata={
             "rule_kind": "temporal",
             "temporal_kind": "sequence",
             "source_tags": [...],
             "supporting_frame_indices": (7, 7, 9),
             "review_family": "cut_in",
             "review_priority": 10,
             ...
           })

═══════════════════════════════════════════════════════════════
阶段 4: 事件策略 (POLICY 层)
═══════════════════════════════════════════════════════════════

9. EventPolicyEngine.apply(all_events, all_rules):

   所有事件（包括 debug/supporting/review）进入管道:

   [层 1 - Cooldown]:
     adjacent_vehicle: 无冷却配置 → 直接通过
     cut_in_confirmed: 无冷却配置 → 直接通过
     sdc_hard_braking: cooldown_frames=20 → 帧 11 保留, 帧 12-30 丢弃

   [层 2 - Compact]:
     adjacent_vehicle (intent=supporting, compact=by_subject):
       帧 7-9 连续触发 → 合并为一个区间事件
       metadata.compaction = {
         start_frame_index: 7, end_frame_index: 9,
         frame_count: 3, raw_frame_indices: (7, 8, 9)
       }
     cut_in_confirmed (intent=review): 不压缩（留给 episode）

   [层 3 - Episode]:
     cut_in_confirmed (intent=review, episode=by_subject):
       如果帧 9-10 都有 cut_in_confirmed 事件 → 合并
       metadata.episode = {
         start_frame_index: 9, end_frame_index: 10,
         event_count: 2,
         supporting_frame_indices: (7, 7, 8, 9),
         supporting_timestamps_seconds: (...)
       }

   [层 4 - Review Dominance]:
     cut_in 家族: cut_in_confirmed (priority=10), cut_in_risk (priority=20)
     如果两者在同一 subject 上触发且区间重叠:
       cut_in_confirmed 被 cut_in_risk 覆盖 → 丢弃 cut_in_confirmed

═══════════════════════════════════════════════════════════════
最终输出
═══════════════════════════════════════════════════════════════

EngineResult(
  scenario_id="3a7b9c...",
  events=(
    TagEvent(tag="cut_in_confirmed", subject_id="103:207", ...),
    TagEvent(tag="sdc_hard_braking", subject_id="103:311", ...),
    ...  # 共约 20-100 个最终事件
  ),
  stats=EngineStats(input_frames=11, future_frames=50, ...)
)
```

---

## 5. 关键设计决策与权衡

### 5.1 为什么门控规则用"拓扑迭代"而非"依赖图"？

当前的迭代式拓扑执行很朴素——每轮扫描所有 pending 规则，找出前置已完成的那批，执行，更新 completed_tags，下一轮继续。

**替代方案：** 构建完整的依赖图，拓扑排序后一次性确定执行顺序。

**WHY 没这样做？**
- 依赖关系是动态的：门控规则是否执行取决于前置标签是否有事件产生（运行时才知道）
- 当前实现的最坏情况 O(R²)（R=门控规则数），但 R 通常很小（< 10）
- 简单性：while + 计数器 + fallback 的模式比完整 DAG 实现更容易理解和维护

### 5.2 为什么 SDC 变体和通用变体分开定义？

有 `agent` 和 `sdc_agent`、`agent_pair` 和 `sdc_pair` ——为什么不直接用 `agent` + 参数？

**原因：**
1. **候选对生成的复杂度不同：** `agent_pair` 是 O(n²)，`sdc_pair` 是 O(n)
2. **自动元数据附加：** `sdc_pair` 规则自动在事件中附加 `ego_id`/`ego_role`/`target_role`，不需要在 YAML 中手动声明
3. **语义清晰：** 规则作者明确知道这条规则是"SDC 视角"还是"通用视角"

### 5.3 为什么 Policy 分四层而非合并？

如果只用一层（比如 episode），逻辑上也能覆盖大部分场景。但分层设计提供了组合灵活性：

- 有些规则只需要 cooldown（如 `sdc_hard_braking`）
- 有些只需要 compact（如 `adjacent_vehicle`，它是 supporting 信号）
- 有些需要 episode（review 事件）
- Dominance 是跨规则的，必须在所有规则的事件产生后统一处理

分层让每个规则可以**独立声明自己需要哪种后处理**，而不是被全局统一策略限制。

---

## 6. 三模块的边界与耦合

```
┌──────────────────────────────────────────────────────────────┐
│                      耦合关系                                 │
│                                                              │
│  RULES ◄──────── ENGINE ────────► POLICY                     │
│  (只读)          (读写)            (只读, 产生新事件)          │
│                                                              │
│  RULES 产出 ExecutionPlan → ENGINE 消费                      │
│  ENGINE 产出 TagEvent[] → POLICY 消费                        │
│  POLICY 产出 TagEvent[] → 外部消费者 (viewer/payload)         │
│                                                              │
│  RULES 和 POLICY 之间没有直接依赖                              │
│  ENGINE 是唯一的"编排者"                                      │
└──────────────────────────────────────────────────────────────┘
```

**耦合最小化原则：**

- **RULES 不知道 ENGINE 的存在。** Parser/Compiler 只产出数据结构（ExecutionPlan），不关心谁消费它
- **ENGINE 不知道 POLICY 的存在。** TriggerEngine 只负责调用 `policy_engine.apply()`，不关心内部逻辑
- **POLICY 只依赖 TagEvent 和 Rule 的数据结构。** 不需要知道事件是怎么产生的

这意味着：可以替换 Parser（如支持 JSON 格式）、替换 Policy（如加入新的去重策略）、甚至替换整个 RuleEngine 的实现——只要接口不变。

---

*分析完成时间：2026-07-02 | 聚焦模块：Engine / Rules / Policy*
*覆盖文件：engine/trigger_engine.py, engine/subjects.py, engine/event_policy.py, engine/timeline.py, engine/compiler.py, engine/registry.py, rules/parser.py, rules/ast.py, rules/engine.py, rules/events.py*
