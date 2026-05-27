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


if __name__ == "__main__":
    unittest.main()
