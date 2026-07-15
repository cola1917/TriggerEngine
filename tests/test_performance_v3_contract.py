import unittest

from tests.test_performance_v2_contract import (
    CountingPairOperator,
    SPATIAL_PAIR_RULE_YAML,
    agent,
)
from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import Frame


def make_sparse_context(agent_count=60):
    agents = [agent(0, 0.0, 0.0), agent(1, 3.0, 0.5)]
    for track_id in range(2, agent_count):
        agents.append(agent(track_id, 1000.0 + track_id * 20.0, 1000.0))

    frame = AlignedFrame(
        frame=Frame(
            scenario_id="scenario-performance-v3",
            step_index=0,
            timestamp_seconds=0.0,
            phase="current",
            agent_states=tuple(agents),
            traffic_lights=(),
        ),
        visibility="current",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )
    return AlignmentContext(
        scenario_id="scenario-performance-v3",
        watermark=Watermark("scenario-performance-v3", 0, 0.0),
        observed_frames=(),
        current_frame=frame,
        future_frames=(),
        input_frames=(frame,),
        source="unit",
    )


def make_sparse_sdc_context(agent_count=60):
    ctx = make_sparse_context(agent_count=agent_count)
    return AlignmentContext(
        scenario_id=ctx.scenario_id,
        watermark=ctx.watermark,
        observed_frames=ctx.observed_frames,
        current_frame=ctx.current_frame,
        future_frames=ctx.future_frames,
        input_frames=ctx.input_frames,
        source=ctx.source,
        map_features=ctx.map_features,
        sdc_track_index=0,
        sdc_track_id=0,
    )


SPATIAL_SDC_PAIR_RULE_YAML = """
rules:
  - id: nearby_sdc_pair
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.count_pair
        - operator: predicate.close_lateral_gap
          args:
            max_lateral_m: 2.0
            max_longitudinal_m: 5.0
    emit:
      tag: nearby_sdc_pair
"""


class PerformanceV3ContractTests(unittest.TestCase):
    def test_spatial_broad_phase_limits_exact_pair_scan_for_bounded_pair_rules(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        register_builtin_operators(registry)
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(SPATIAL_PAIR_RULE_YAML)
        context = make_sparse_context(agent_count=60)
        cache = SubjectCache()

        events = RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual([event.subject_id for event in events], ["0:1", "1:0"])
        self.assertEqual(cache.rule_candidate_count("nearby_pair", "agent_pair", 0), 2)
        self.assertLess(cache.rule_pair_scan_count("nearby_pair", "agent_pair", 0), 20)

    def test_spatial_broad_phase_preserves_output_against_uncached_full_scan(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        cached_counter = CountingPairOperator()
        cached_registry = OperatorRegistry()
        register_builtin_operators(cached_registry)
        cached_registry.register(cached_counter)

        uncached_counter = CountingPairOperator()
        uncached_registry = OperatorRegistry()
        register_builtin_operators(uncached_registry)
        uncached_registry.register(uncached_counter)

        rule_set = RuleParser().parse_yaml(SPATIAL_PAIR_RULE_YAML)
        context = make_sparse_context(agent_count=60)

        cached_events = RuleEngine(cached_registry).evaluate(
            rule_set, context, subject_cache=SubjectCache()
        )
        uncached_events = RuleEngine(uncached_registry).evaluate(rule_set, context)

        self.assertEqual(
            [(event.tag_name, event.subject_id) for event in cached_events],
            [(event.tag_name, event.subject_id) for event in uncached_events],
        )
        self.assertLess(len(cached_counter.calls), len(uncached_counter.calls))
        self.assertEqual(len(uncached_counter.calls), 60 * 59)

    def test_sdc_pair_candidate_generation_scans_only_sdc_to_targets(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        register_builtin_operators(registry)
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(SPATIAL_SDC_PAIR_RULE_YAML)
        context = make_sparse_sdc_context(agent_count=60)
        cache = SubjectCache()

        events = RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual([event.subject_id for event in events], ["0:1"])
        self.assertEqual(counter.calls, ["0:1"])
        self.assertEqual(cache.rule_candidate_count("nearby_sdc_pair", "sdc_pair", 0), 1)
        self.assertLessEqual(cache.rule_pair_scan_count("nearby_sdc_pair", "sdc_pair", 0), 59)

    def test_low_ttc_candidate_generation_filters_non_closing_pairs(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        register_builtin_operators(registry)
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: closing_low_ttc_candidates
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.count_pair
        - operator: predicate.low_ttc
          args:
            threshold_s: 3.0
            max_lateral_m: 2.0
            min_closing_speed_mps: 1.0
    emit:
      tag: closing_low_ttc_candidates
"""
        )
        context = make_sparse_sdc_context(agent_count=4)
        agents = list(context.current_frame.frame.agent_states)
        agents[0] = agent(0, 0.0, 0.0)
        agents[0] = type(agents[0])(
            **{**agents[0].__dict__, "velocity_x": 5.0}
        )
        agents[1] = type(agents[1])(
            **{**agents[1].__dict__, "velocity_x": 2.0}
        )
        agents[2] = agent(2, 4.0, 0.0)
        agents[2] = type(agents[2])(
            **{**agents[2].__dict__, "velocity_x": 5.0}
        )
        updated_frame = type(context.current_frame.frame)(
            **{**context.current_frame.frame.__dict__, "agent_states": tuple(agents)}
        )
        updated_aligned = type(context.current_frame)(
            frame=updated_frame,
            visibility=context.current_frame.visibility,
            available_modalities=context.current_frame.available_modalities,
        )
        context = AlignmentContext(
            scenario_id=context.scenario_id,
            watermark=context.watermark,
            observed_frames=(),
            current_frame=updated_aligned,
            future_frames=(),
            input_frames=(updated_aligned,),
            source=context.source,
            map_features=context.map_features,
            sdc_track_index=context.sdc_track_index,
            sdc_track_id=context.sdc_track_id,
        )
        cache = SubjectCache()

        RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(counter.calls, ["0:1"])
        self.assertEqual(
            cache.rule_candidate_count("closing_low_ttc_candidates", "sdc_pair", 0),
            1,
        )

    def test_lane_change_conflict_candidate_generation_filters_stationary_targets(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        register_builtin_operators(registry)
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: moving_lane_change_conflict_candidates
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.count_pair
        - operator: predicate.sdc_lane_change_conflict
          args:
            max_front_longitudinal_m: 25.0
            max_behind_longitudinal_m: 20.0
            max_lateral_m: 3.0
            min_target_speed_mps: 1.0
    emit:
      tag: moving_lane_change_conflict_candidates
"""
        )
        context = make_sparse_sdc_context(agent_count=4)
        agents = list(context.current_frame.frame.agent_states)
        agents[1] = type(agents[1])(
            **{**agents[1].__dict__, "velocity_x": 2.0}
        )
        agents[2] = agent(2, 6.0, 0.0)
        updated_frame = type(context.current_frame.frame)(
            **{**context.current_frame.frame.__dict__, "agent_states": tuple(agents)}
        )
        updated_aligned = type(context.current_frame)(
            frame=updated_frame,
            visibility=context.current_frame.visibility,
            available_modalities=context.current_frame.available_modalities,
        )
        context = AlignmentContext(
            scenario_id=context.scenario_id,
            watermark=context.watermark,
            observed_frames=(),
            current_frame=updated_aligned,
            future_frames=(),
            input_frames=(updated_aligned,),
            source=context.source,
            map_features=context.map_features,
            sdc_track_index=context.sdc_track_index,
            sdc_track_id=context.sdc_track_id,
        )
        cache = SubjectCache()

        RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(counter.calls, ["0:1"])
        self.assertEqual(
            cache.rule_candidate_count("moving_lane_change_conflict_candidates", "sdc_pair", 0),
            1,
        )

    def test_lane_change_conflict_pair_generation_skips_when_sdc_lateral_motion_too_small(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        register_builtin_operators(registry)
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: moving_lane_change_conflict_candidates
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.count_pair
        - operator: predicate.sdc_lane_change_conflict
          args:
            window_seconds: 3.0
            max_front_longitudinal_m: 25.0
            max_behind_longitudinal_m: 20.0
            max_lateral_m: 3.0
            min_lateral_displacement_m: 1.5
            min_target_speed_mps: 1.0
    emit:
      tag: moving_lane_change_conflict_candidates
"""
        )
        past_agents = (
            type(agent(0, 0.0, 0.0))(**{**agent(0, 0.0, 0.0).__dict__, "velocity_x": 6.0}),
            type(agent(1, 10.0, 0.0))(**{**agent(1, 10.0, 0.0).__dict__, "velocity_x": 3.0}),
        )
        current_agents = (
            type(agent(0, 3.0, 0.2))(**{**agent(0, 3.0, 0.2).__dict__, "velocity_x": 6.0, "timestamp_seconds": 1.0}),
            type(agent(1, 12.0, 0.0))(**{**agent(1, 12.0, 0.0).__dict__, "velocity_x": 3.0, "timestamp_seconds": 1.0}),
        )
        past_frame = AlignedFrame(
            frame=Frame(
                scenario_id="scenario-lane-change-conflict-gate",
                step_index=0,
                timestamp_seconds=0.0,
                phase="history",
                agent_states=past_agents,
                traffic_lights=(),
            ),
            visibility="observed",
            available_modalities=frozenset({"agents", "valid_agents"}),
        )
        current_frame = AlignedFrame(
            frame=Frame(
                scenario_id="scenario-lane-change-conflict-gate",
                step_index=10,
                timestamp_seconds=1.0,
                phase="current",
                agent_states=current_agents,
                traffic_lights=(),
            ),
            visibility="current",
            available_modalities=frozenset({"agents", "valid_agents"}),
        )
        context = AlignmentContext(
            scenario_id="scenario-lane-change-conflict-gate",
            watermark=Watermark("scenario-lane-change-conflict-gate", 10, 1.0),
            observed_frames=(past_frame,),
            current_frame=current_frame,
            future_frames=(),
            input_frames=(past_frame, current_frame),
            source="unit",
            sdc_track_index=0,
            sdc_track_id=0,
        )
        cache = SubjectCache()

        RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(counter.calls, [])
        self.assertEqual(
            cache.rule_candidate_count("moving_lane_change_conflict_candidates", "sdc_pair", 10),
            0,
        )
        self.assertEqual(
            cache.rule_pair_scan_count("moving_lane_change_conflict_candidates", "sdc_pair", 10),
            0,
        )
        self.assertEqual(
            cache.rule_geometry_mode("moving_lane_change_conflict_candidates", "sdc_pair", 10),
            "sdc_motion_gate",
        )

    def test_classic_expensive_lane_review_rules_only_run_on_current_frame(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rule_set = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML)
        by_id = {rule.rule_id: rule for rule in rule_set.rules}

        for rule_id, operator_name in (
            ("lane_change_conflict", "predicate.sdc_lane_change_conflict"),
            ("sdc_repeated_lane_change", "predicate.sdc_repeated_lane_change"),
        ):
            rule = by_id[rule_id]
            call = next(
                call
                for call in rule.condition.calls
                if call.operator_name == operator_name
            )
            self.assertTrue(call.args["only_current_frame"])

    def test_sdc_hard_braking_pair_generation_skips_when_ego_not_braking(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        register_builtin_operators(registry)
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: hard_braking_pair_candidates
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.count_pair
        - operator: predicate.pair_ego_hard_braking
          args:
            window_seconds: 1.0
            max_acceleration_mps2: -3.0
            min_speed_drop_mps: 2.0
            min_start_speed_mps: 3.0
            max_front_longitudinal_m: 35.0
            max_lateral_m: 4.0
    emit:
      tag: hard_braking_pair_candidates
"""
        )
        past_agents = (
            type(agent(0, 0.0, 0.0))(**{**agent(0, 0.0, 0.0).__dict__, "velocity_x": 10.0}),
            type(agent(1, 20.0, 0.0))(**{**agent(1, 20.0, 0.0).__dict__, "velocity_x": 5.0}),
        )
        current_agents = (
            type(agent(0, 8.0, 0.0))(**{**agent(0, 8.0, 0.0).__dict__, "velocity_x": 9.0, "timestamp_seconds": 1.0}),
            type(agent(1, 24.0, 0.0))(**{**agent(1, 24.0, 0.0).__dict__, "velocity_x": 5.0, "timestamp_seconds": 1.0}),
        )
        past_frame = AlignedFrame(
            frame=Frame(
                scenario_id="scenario-hard-brake-gate",
                step_index=0,
                timestamp_seconds=0.0,
                phase="history",
                agent_states=past_agents,
                traffic_lights=(),
            ),
            visibility="observed",
            available_modalities=frozenset({"agents", "valid_agents"}),
        )
        current_frame = AlignedFrame(
            frame=Frame(
                scenario_id="scenario-hard-brake-gate",
                step_index=10,
                timestamp_seconds=1.0,
                phase="current",
                agent_states=current_agents,
                traffic_lights=(),
            ),
            visibility="current",
            available_modalities=frozenset({"agents", "valid_agents"}),
        )
        context = AlignmentContext(
            scenario_id="scenario-hard-brake-gate",
            watermark=Watermark("scenario-hard-brake-gate", 10, 1.0),
            observed_frames=(past_frame,),
            current_frame=current_frame,
            future_frames=(),
            input_frames=(past_frame, current_frame),
            source="unit",
            sdc_track_index=0,
            sdc_track_id=0,
        )
        cache = SubjectCache()

        RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(counter.calls, [])
        self.assertEqual(
            cache.rule_candidate_count("hard_braking_pair_candidates", "sdc_pair", 10),
            0,
        )
        self.assertEqual(
            cache.rule_pair_scan_count("hard_braking_pair_candidates", "sdc_pair", 10),
            0,
        )
        self.assertEqual(
            cache.rule_geometry_mode("hard_braking_pair_candidates", "sdc_pair", 10),
            "sdc_motion_gate",
        )

    def test_sdc_hard_braking_pair_generation_keeps_candidates_when_ego_brakes(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        register_builtin_operators(registry)
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: hard_braking_pair_candidates
    kind: single_frame
    subject: sdc_pair
    when:
      all:
        - operator: predicate.count_pair
        - operator: predicate.pair_ego_hard_braking
          args:
            window_seconds: 1.0
            max_acceleration_mps2: -3.0
            min_speed_drop_mps: 2.0
            min_start_speed_mps: 3.0
            max_front_longitudinal_m: 35.0
            max_lateral_m: 4.0
    emit:
      tag: hard_braking_pair_candidates
"""
        )
        past_agents = (
            type(agent(0, 0.0, 0.0))(**{**agent(0, 0.0, 0.0).__dict__, "velocity_x": 12.0}),
            type(agent(1, 20.0, 0.0))(**{**agent(1, 20.0, 0.0).__dict__, "velocity_x": 5.0}),
        )
        current_agents = (
            type(agent(0, 8.0, 0.0))(**{**agent(0, 8.0, 0.0).__dict__, "velocity_x": 7.0, "timestamp_seconds": 1.0}),
            type(agent(1, 24.0, 0.0))(**{**agent(1, 24.0, 0.0).__dict__, "velocity_x": 5.0, "timestamp_seconds": 1.0}),
        )
        past_frame = AlignedFrame(
            frame=Frame(
                scenario_id="scenario-hard-brake-gate",
                step_index=0,
                timestamp_seconds=0.0,
                phase="history",
                agent_states=past_agents,
                traffic_lights=(),
            ),
            visibility="observed",
            available_modalities=frozenset({"agents", "valid_agents"}),
        )
        current_frame = AlignedFrame(
            frame=Frame(
                scenario_id="scenario-hard-brake-gate",
                step_index=10,
                timestamp_seconds=1.0,
                phase="current",
                agent_states=current_agents,
                traffic_lights=(),
            ),
            visibility="current",
            available_modalities=frozenset({"agents", "valid_agents"}),
        )
        context = AlignmentContext(
            scenario_id="scenario-hard-brake-gate",
            watermark=Watermark("scenario-hard-brake-gate", 10, 1.0),
            observed_frames=(past_frame,),
            current_frame=current_frame,
            future_frames=(),
            input_frames=(past_frame, current_frame),
            source="unit",
            sdc_track_index=0,
            sdc_track_id=0,
        )
        cache = SubjectCache()

        RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(counter.calls, ["0:1"])
        self.assertEqual(
            cache.rule_candidate_count("hard_braking_pair_candidates", "sdc_pair", 10),
            1,
        )


if __name__ == "__main__":
    unittest.main()
