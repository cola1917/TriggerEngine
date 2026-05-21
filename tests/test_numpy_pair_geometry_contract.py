import unittest

from tests.test_performance_v2_contract import (
    CountingPairOperator,
    SPATIAL_PAIR_RULE_YAML,
    agent,
)
from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import Frame


def make_numpy_context(agent_count=40):
    agents = [agent(0, 0.0, 0.0), agent(1, 3.0, 0.5)]
    for track_id in range(2, agent_count):
        agents.append(agent(track_id, 100.0 + track_id * 20.0, 100.0))

    frame = AlignedFrame(
        frame=Frame(
            scenario_id="scenario-numpy-geometry",
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
        scenario_id="scenario-numpy-geometry",
        watermark=Watermark("scenario-numpy-geometry", 0, 0.0),
        observed_frames=(),
        current_frame=frame,
        future_frames=(),
        input_frames=(frame,),
        source="unit",
    )


class NumpyPairGeometryContractTests(unittest.TestCase):
    def test_numpy_pair_geometry_preserves_candidate_output(self):
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
        context = make_numpy_context(agent_count=40)
        cache = SubjectCache()

        cached_events = RuleEngine(cached_registry).evaluate(
            rule_set,
            context,
            subject_cache=cache,
        )
        uncached_events = RuleEngine(uncached_registry).evaluate(rule_set, context)

        self.assertEqual(
            [(event.tag_name, event.subject_id) for event in cached_events],
            [(event.tag_name, event.subject_id) for event in uncached_events],
        )
        self.assertEqual(cache.rule_geometry_mode("nearby_pair", "agent_pair", 0), "numpy")
        self.assertEqual(cache.rule_candidate_count("nearby_pair", "agent_pair", 0), 2)
        self.assertLess(len(cached_counter.calls), len(uncached_counter.calls))

    def test_small_agent_count_uses_scalar_geometry(self):
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
        context = make_numpy_context(agent_count=10)
        cache = SubjectCache()

        RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(cache.rule_geometry_mode("nearby_pair", "agent_pair", 0), "scalar")


if __name__ == "__main__":
    unittest.main()
