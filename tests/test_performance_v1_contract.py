import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D
from trigger_engine.rules.events import TagEvent


PAIR_RULES_YAML = """
rules:
  - id: pair_rule_a
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_counter_a
    emit:
      tag: pair_a

  - id: pair_rule_b
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_counter_b
    emit:
      tag: pair_b
"""


TEMPORAL_PAIR_YAML = """
rules:
  - id: pair_start
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_start
    emit:
      tag: pair_start

  - id: pair_end
    kind: single_frame
    subject: agent_pair
    when:
      all:
        - operator: predicate.pair_end
    emit:
      tag: pair_end

  - id: pair_sequence
    kind: temporal
    subject: agent_pair
    when:
      sequence:
        - tag: pair_start
        - tag: pair_end
      within_frames: 3
    emit:
      tag: pair_sequence
"""


def agent(track_id, valid=True):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(0.0, 0.0, 0.0),
        velocity_x=0.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=valid,
    )


def aligned_frame(step_index, agents):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-performance",
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase="current" if step_index == 2 else "history",
            agent_states=agents,
            traffic_lights=(),
        ),
        visibility="current" if step_index == 2 else "observed",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def make_context(agent_count=8, frame_count=3):
    frames = tuple(
        aligned_frame(i, tuple(agent(track_id) for track_id in range(agent_count)))
        for i in range(frame_count)
    )
    return AlignmentContext(
        scenario_id="scenario-performance",
        watermark=Watermark(
            "scenario-performance",
            frames[-1].frame.step_index,
            frames[-1].frame.timestamp_seconds,
        ),
        observed_frames=frames[:-1],
        current_frame=frames[-1],
        future_frames=(),
        input_frames=frames,
        source="unit",
    )


class PairCounterAOperator:
    name = "predicate.pair_counter_a"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.subject_id == "0:1",
            {},
        )


class PairCounterBOperator(PairCounterAOperator):
    name = "predicate.pair_counter_b"


class PairStartOperator(PairCounterAOperator):
    name = "predicate.pair_start"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.subject_id == "0:1" and frame.frame.step_index == 0,
            {},
        )


class PairEndOperator(PairCounterAOperator):
    name = "predicate.pair_end"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            self.name,
            "agent_pair",
            subject.subject_id,
            frame.frame.step_index,
            frame.frame.timestamp_seconds,
            subject.subject_id == "0:1" and frame.frame.step_index == 2,
            {},
        )


class PerformanceV1ContractTests(unittest.TestCase):
    def test_subject_cache_builds_agent_pairs_once_per_frame(self):
        from trigger_engine.engine.subjects import SubjectCache

        context = make_context(agent_count=5, frame_count=1)
        cache = SubjectCache()
        frame = context.current_frame

        first = cache.subjects_for("agent_pair", frame)
        second = cache.subjects_for("agent_pair", frame)

        self.assertIs(first, second)
        self.assertEqual(len(first), 20)
        self.assertEqual(cache.build_count("agent_pair", frame.frame.step_index), 1)

    def test_rule_engine_reuses_subject_cache_across_pair_rules(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(PairCounterAOperator())
        registry.register(PairCounterBOperator())
        rule_set = RuleParser().parse_yaml(PAIR_RULES_YAML)
        context = make_context(agent_count=6, frame_count=3)
        cache = SubjectCache()

        events = RuleEngine(registry).evaluate(rule_set, context, subject_cache=cache)

        self.assertEqual(
            [event.tag_name for event in events],
            ["pair_a", "pair_a", "pair_a", "pair_b", "pair_b", "pair_b"],
        )
        self.assertEqual(
            [cache.build_count("agent_pair", frame.frame.step_index) for frame in context.input_frames],
            [1, 1, 1],
        )

    def test_tag_timeline_exposes_indexed_subjects_and_frames(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline

        timeline = TagTimeline.from_events(
            (
                TagEvent("s", None, 0, 0.0, "pair_start", "agent_pair", "0:1", True, "r1", {}),
                TagEvent("s", None, 2, 0.2, "pair_start", "agent_pair", "0:1", True, "r1", {}),
                TagEvent("s", None, 1, 0.1, "pair_start", "agent_pair", "1:2", True, "r1", {}),
            )
        )

        self.assertEqual(
            timeline.subject_ids_for("pair_start", "agent_pair"),
            ("0:1", "1:2"),
        )
        self.assertEqual(
            timeline.frames_for(TagKey("pair_start", "agent_pair", "0:1")),
            (0, 2),
        )

    def test_temporal_engine_does_not_build_all_agent_pairs_for_sequence_rules(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.registry import OperatorRegistry

        operators = OperatorRegistry()
        operators.register(PairStartOperator())
        operators.register(PairEndOperator())
        rules = RuleRegistry(operator_registry=operators)
        rules.register_yaml("perf", TEMPORAL_PAIR_YAML)
        rules.activate("perf")
        context = make_context(agent_count=8, frame_count=3)
        cache = SubjectCache()

        result = TriggerEngine(operators, rules, subject_cache=cache).evaluate(context)

        self.assertIn("pair_sequence", {event.tag_name for event in result.events})
        self.assertEqual(
            [cache.build_count("agent_pair", frame.frame.step_index) for frame in context.input_frames],
            [1, 1, 1],
        )

    def test_temporal_engine_uses_timeline_candidates_without_subject_cache_pair_builds(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.engine.timeline import TagTimeline
        from trigger_engine.engine.trigger_engine import TemporalRuleEngine
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.ast import RuleSet
        from trigger_engine.rules.engine import RuleEngine

        operators = OperatorRegistry()
        operators.register(PairStartOperator())
        operators.register(PairEndOperator())
        rules = RuleRegistry(operator_registry=operators)
        plan = rules.register_yaml("perf", TEMPORAL_PAIR_YAML)
        context = make_context(agent_count=8, frame_count=3)

        single_events = RuleEngine(operators).evaluate(
            RuleSet(rules=plan.single_frame_rules),
            context,
        )
        timeline = TagTimeline.from_events(single_events)
        cache = SubjectCache()

        temporal_events = TemporalRuleEngine().evaluate(
            plan.temporal_rules,
            context,
            timeline,
            subject_cache=cache,
        )

        self.assertEqual([event.tag_name for event in temporal_events], ["pair_sequence"])
        self.assertEqual(
            [cache.build_count("agent_pair", frame.frame.step_index) for frame in context.input_frames],
            [0, 0, 0],
        )


if __name__ == "__main__":
    unittest.main()
