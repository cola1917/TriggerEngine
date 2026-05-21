# Core Engine 任务拆分

这是交给 worker 的任务清单。每完成一项，请把 `[ ]` 改成 `[x]`，并确认对应测试通过。

## Task 1: 扩展 Rule AST 和 Parser

- [x] 给 `Rule` 增加 `kind`
- [x] 实现 `SustainedTagCondition`
- [x] Parser 支持 `kind: single_frame`
- [x] Parser 支持 `kind: temporal`
- [x] Parser 将 `when.tag + sustained.frames` 解析为 `SustainedTagCondition`
- [x] Parser 拒绝 temporal rule 中出现 `operator`
- [x] Parser 保持旧 single-frame YAML 兼容，默认 kind 为 `single_frame`

验收：

- `tests/test_rule_dsl_temporal_contract.py` 通过。

## Task 2: 实现 ExecutionPlan 和 RuleCompiler

- [x] 创建 `trigger_engine/engine/__init__.py`
- [x] 创建 `trigger_engine/engine/compiler.py`
- [x] 实现 `ExecutionPlan`
- [x] 实现 `RuleCompiler`
- [x] 实现 `RuleCompileError`
- [x] 按 kind 拆分 single-frame rules 和 temporal rules
- [x] 校验 single-frame operator 已注册
- [x] 校验 operator subject 匹配 rule subject
- [x] 校验 operator result_kind 为 predicate
- [x] 校验 temporal source tag 来自 single-frame emit tag
- [x] 校验 temporal `sustained.frames` 为正整数
- [x] 校验 temporal rule 不引用 operator

验收：

- `tests/test_rule_compiler_contract.py` 通过。

## Task 3: 实现 RuleRegistry

- [x] 创建 `trigger_engine/engine/registry.py`
- [x] 实现 `RuleRegistry`
- [x] 实现 `RuleRegistryError`
- [x] 支持 `register(plan)`
- [x] 支持 `register_yaml(name, yaml_text)`
- [x] 支持 `activate(plan_id)`
- [x] 支持 `active_plan()`
- [x] 未激活 plan 时给清晰错误
- [x] 未注册 operator 时注册 YAML 失败

验收：

- `tests/test_rule_registry_contract.py` 通过。

## Task 4: 实现 TagTimeline

- [x] 创建 `trigger_engine/engine/timeline.py`
- [x] 实现 `TagKey`
- [x] 实现 `TagTimeline.from_events`
- [x] 实现 `has_at`
- [x] 实现 `sustained`
- [x] sustained 返回支撑 frame indices
- [x] 不跨 subject 拼接 tag

验收：

- `tests/test_tag_timeline_contract.py` 通过。

## Task 5: 实现 TriggerEngine 和 TemporalRuleEngine

- [x] 创建 `trigger_engine/engine/trigger_engine.py`
- [x] 实现 `EngineStats`
- [x] 实现 `EngineDiagnostic`
- [x] 实现 `EngineResult`
- [x] 实现 `TemporalRuleEngine`
- [x] 实现 `TriggerEngine.evaluate(context)`
- [x] `evaluate` 不接收 YAML
- [x] `evaluate` 不接收 ScenarioBundle
- [x] 运行 active plan 的 single-frame rules
- [x] 基于 single-frame events 构造 TagTimeline
- [x] 运行 temporal rules
- [x] 输出 single-frame + temporal TagEvents
- [x] stats 正确记录 input/future/rule/event 数
- [x] future frame 不进入输出

验收：

- `tests/test_trigger_engine_contract.py` 通过。
