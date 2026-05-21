# Rule / Operator / TagEvent 任务拆分

这是给 worker 执行的任务清单。每完成一项，请把 `[ ]` 改成 `[x]`，并确认对应测试通过。

## Task 1: 建立 Operator schema 和 registry

- [x] 创建 `trigger_engine/operators/__init__.py`
- [x] 创建 `trigger_engine/operators/base.py`
- [x] 创建 `trigger_engine/operators/registry.py`
- [x] 实现 `OperatorResult`
- [x] 实现 `OperatorRegistry`
- [x] 实现 `OperatorRegistryError`
- [x] 支持 operator 注册、查找、列出名称
- [x] 拒绝重复注册
- [x] 缺失 operator 给清晰错误

验收：

- `tests/test_operator_registry_contract.py` 通过。

## Task 2: 建立 Rule AST 和 TagEvent schema

- [x] 创建 `trigger_engine/rules/__init__.py`
- [x] 创建 `trigger_engine/rules/ast.py`
- [x] 创建 `trigger_engine/rules/events.py`
- [x] 实现 `RuleSet`
- [x] 实现 `Rule`
- [x] 实现 `RuleWindow`
- [x] 实现 `OperatorCall`
- [x] 实现 `AllCondition`
- [x] 实现 `RuleEmit`
- [x] 实现 `TagEvent`

验收：

- AST dataclass contract 测试通过。
- TagEvent 字段可表达 scenario/source/frame/subject/tag/rule。

## Task 3: 实现 Rule YAML parser

- [x] 创建 `trigger_engine/rules/parser.py`
- [x] 实现 `RuleParser`
- [x] 实现 `RuleParseError`
- [x] 支持顶层 `rules`
- [x] 支持 `when.all`
- [x] 支持 `emit.tag`
- [x] 支持 `window.history_steps`
- [x] 拒绝重复 rule id
- [x] 拒绝非法 subject
- [x] 拒绝未知 condition 形态

验收：

- YAML 能解析成 RuleSet AST。
- 错误配置有清晰异常。

## Task 4: 实现 RuleEngine MVP

- [x] 创建 `trigger_engine/rules/engine.py`
- [x] 实现 `RuleEngine`
- [x] 只遍历 `AlignmentContext.input_frames`
- [x] 支持 agent subject
- [x] 支持 frame subject
- [x] 支持 `when.all`
- [x] 调用 `OperatorRegistry` 查找 operator
- [x] 所有 predicate 为 true 时输出 `TagEvent`
- [x] operator 缺失时给清晰错误
- [x] future frame 不进入输出

验收：

- `tests/test_rule_engine_contract.py` 通过。
- future 泄漏防护测试通过。

## Task 5: 实现 JSONL writer contract

- [x] 创建 `trigger_engine/rules/writers.py`
- [x] 实现 `tag_event_to_dict`
- [x] 实现 `JsonlTagEventWriter.write_many`
- [x] 每行输出一个 TagEvent JSON

验收：

- `tests/test_tag_event_writer_contract.py` 通过。
