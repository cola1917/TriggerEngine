# Scenario Packs 任务拆分

这是交给 worker 的任务清单。每完成一项，请把 `[ ]` 改成 `[x]`，并确认对应测试通过。

## Task 1: 支持 agent_pair subject

- [x] 实现 `AgentPairSubject`
- [x] RuleParser 允许 `subject: agent_pair`
- [x] RuleEngine 支持生成 agent pair subjects
- [x] RuleEngine 输出 pair subject_id 为 `"ego_id:other_id"`
- [x] pair 不包含同一 track
- [x] pair 只使用当前 frame

验收：

- `tests/test_agent_pair_subject_contract.py` 通过。

## Task 2: 实现 built-in operator registry

- [x] 创建 `trigger_engine/operators/builtins.py`
- [x] 实现 `register_builtin_operators`
- [x] 重复注册时跳过已有 operator
- [x] 实现 `predicate.type_is`
- [x] 实现 `predicate.speed_below`
- [x] 实现 `predicate.speed_above`
- [x] 实现 `predicate.pair_types_are`
- [x] 实现 `predicate.pair_in_front`
- [x] 实现 `predicate.low_ttc`
- [x] 实现 `predicate.close_lateral_gap`
- [x] 实现 `predicate.lateral_motion_toward`
- [x] 实现 `predicate.heading_converging`
- [x] 实现 `predicate.near_red_light_stop_point`

验收：

- `tests/test_builtin_operators_contract.py` 通过。

## Task 3: 实现 classic scenario YAML pack

- [x] 创建 `trigger_engine/scenarios/__init__.py`
- [x] 创建 `trigger_engine/scenarios/classic.py`
- [x] 定义 `CLASSIC_SCENARIO_RULES_YAML`
- [x] 定义 `register_classic_scenario_pack`
- [x] YAML 包含 stopped vehicle rule
- [x] YAML 包含 low TTC rule
- [x] YAML 包含 cut-in candidate rule
- [x] YAML 包含 traffic light interaction rule
- [x] YAML 包含每类至少一个 temporal sustained rule

验收：

- `tests/test_classic_scenario_pack_contract.py` 通过。

## Task 4: 端到端假数据验收

- [x] fake AlignmentContext 能触发 `vehicle_stopped`
- [x] fake AlignmentContext 能触发 `vehicle_stopped_for_3_frames`
- [x] fake AlignmentContext 能触发 `low_ttc_pair`
- [x] fake AlignmentContext 能触发 `persistent_low_ttc_pair`
- [x] fake AlignmentContext 能触发 `cut_in_candidate`
- [x] fake AlignmentContext 能触发 `cut_in_developing`
- [x] fake AlignmentContext 能触发 `vehicle_stopped_at_red`
- [x] fake AlignmentContext 能触发 `vehicle_still_stopped_at_red`
- [x] future frame 不进入 scenario pack 输出

验收：

- `tests/test_classic_scenarios_e2e_contract.py` 通过。
