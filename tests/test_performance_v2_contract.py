import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D


SPATIAL_PAIR_RULE_YAML = """
rules:
  - id: nearby_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.count_pair
        - operator: predicate.close_lateral_gap
          args:
            max_lateral_m: 2.0
            max_longitudinal_m: 5.0
    emit:
      tag: nearby_pair
"""


UNBOUNDED_PAIR_RULE_YAML = """
rules:
  - id: every_pair
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.count_pair
    emit:
      tag: every_pair
"""


def agent(track_id, x, y, heading=0.0):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(x, y, 0.0),
        velocity_x=0.0,
        velocity_y=0.0,
        heading=heading,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def make_context():
    frame = AlignedFrame(
        frame=Frame(
            scenario_id="scenario-performance-v2",
            step_index=0,
            timestamp_seconds=0.0,
            phase="current",
            agent_states=(
                agent(0, 0.0, 0.0),
                agent(1, 3.0, 0.5),
                agent(2, 30.0, 0.0),
                agent(3, 0.0, 20.0),
                agent(4, -30.0, -10.0),
            ),
            traffic_lights=(),
        ),
        visibility="current",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )
    return AlignmentContext(
        scenario_id="scenario-performance-v2",
        watermark=Watermark("scenario-performance-v2", 0, 0.0),
        observed_frames=(),
        current_frame=frame,
        future_frames=(),
        input_frames=(frame,),
        source="unit",
    )


class CountingPairOperator:
    name = "predicate.count_pair"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def __init__(self):
        self.calls = []

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        self.calls.append(subject.subject_id)
        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            True,
            {},
        )


class PerformanceV2ContractTests(unittest.TestCase):
    def test_spatial_pair_rule_automatically_prunes_candidates(self):
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
        context = make_context()
        cache = SubjectCache()

        events = RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(counter.calls, ["0:1", "1:0"])
        self.assertEqual([event.subject_id for event in events], ["0:1", "1:0"])
        self.assertEqual(cache.rule_candidate_count("nearby_pair", "agent_pair", 0), 2)
        self.assertEqual(cache.build_count("agent_pair", 0), 0)

    def test_candidate_pruning_preserves_outputs_against_uncached_rule_engine(self):
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
        context = make_context()

        cached_events = RuleEngine(cached_registry).evaluate(
            rule_set, context, subject_cache=SubjectCache()
        )
        uncached_events = RuleEngine(uncached_registry).evaluate(rule_set, context)

        self.assertEqual(
            [(event.tag_name, event.subject_id) for event in cached_events],
            [(event.tag_name, event.subject_id) for event in uncached_events],
        )
        self.assertEqual(len(cached_counter.calls), 2)
        self.assertEqual(len(uncached_counter.calls), 20)

    def test_unbounded_pair_rule_falls_back_to_full_candidate_set(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        counter = CountingPairOperator()
        registry = OperatorRegistry()
        registry.register(counter)
        rule_set = RuleParser().parse_yaml(UNBOUNDED_PAIR_RULE_YAML)
        context = make_context()
        cache = SubjectCache()

        events = RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(len(counter.calls), 20)
        self.assertEqual(len(events), 20)
        self.assertEqual(cache.build_count("agent_pair", 0), 1)
        self.assertEqual(cache.rule_build_count("every_pair", "agent_pair", 0), 0)

    def test_trigger_engine_uses_default_subject_cache_for_candidate_pruning(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry

        counter = CountingPairOperator()
        operators = OperatorRegistry()
        register_builtin_operators(operators)
        operators.register(counter)
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("perf-v2", SPATIAL_PAIR_RULE_YAML)
        rules.activate("perf-v2")

        result = TriggerEngine(operators, rules).evaluate(make_context())

        self.assertEqual(counter.calls, ["0:1", "1:0"])
        self.assertEqual([event.subject_id for event in result.events], ["0:1", "1:0"])


if __name__ == "__main__":
    unittest.main()
