import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D, ScenarioBundle


def agent(track_id, track_index=None, x=0.0, valid=True):
    return AgentState(
        track_id=track_id,
        track_index=track_id if track_index is None else track_index,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(x, 0.0, 0.0),
        velocity_x=0.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=valid,
    )


def frame(step_index, agents):
    return Frame(
        scenario_id="scenario-sdc",
        step_index=step_index,
        timestamp_seconds=step_index * 0.1,
        phase="current" if step_index == 1 else "history",
        agent_states=tuple(agents),
        traffic_lights=(),
    )


def bundle_with_sdc():
    frames = (
        frame(0, (agent(100, track_index=0), agent(200, track_index=1, x=10.0))),
        frame(1, (agent(100, track_index=0), agent(200, track_index=1, x=10.0), agent(300, track_index=2, x=20.0))),
    )
    return ScenarioBundle(
        scenario_id="scenario-sdc",
        timestamps_seconds=(0.0, 0.1),
        current_time_index=1,
        sdc_track_index=0,
        objects_of_interest=(),
        prediction_targets=(),
        frames=frames,
        map_features={},
        source="unit",
        has_lidar_data=False,
    )


def aligned_context():
    frames = bundle_with_sdc().frames
    aligned = tuple(
        AlignedFrame(
            frame=f,
            visibility="current" if f.step_index == 1 else "observed",
            available_modalities=frozenset({"agents", "valid_agents"}),
        )
        for f in frames
    )
    return AlignmentContext(
        scenario_id="scenario-sdc",
        watermark=Watermark("scenario-sdc", 1, 0.1),
        observed_frames=(aligned[0],),
        current_frame=aligned[1],
        future_frames=(),
        input_frames=aligned,
        source="unit",
        sdc_track_index=0,
        sdc_track_id=100,
    )


class AlwaysSdcAgentTrueOperator:
    name = "predicate.sdc_agent_true"
    result_kind = "predicate"
    subject_type = "agent"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(self.name, "agent", subject.track_id, frame.frame.step_index, frame.frame.timestamp_seconds, True, {})


class AlwaysSdcPairTrueOperator:
    name = "predicate.sdc_pair_true"
    result_kind = "predicate"
    subject_type = "agent_pair"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(self.name, "agent_pair", subject.subject_id, frame.frame.step_index, frame.frame.timestamp_seconds, True, {})


class SdcSubjectContractTests(unittest.TestCase):
    def test_alignment_context_exposes_sdc_identity(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        context = ScenarioAlignment().align(bundle_with_sdc())

        self.assertEqual(context.sdc_track_index, 0)
        self.assertEqual(context.sdc_track_id, 100)

    def test_alignment_rejects_missing_current_sdc_identity(self):
        from trigger_engine.alignment.scenario_alignment import AlignmentError, ScenarioAlignment

        bundle = bundle_with_sdc()
        frames = list(bundle.frames)
        frames[1] = frame(1, (agent(200, track_index=1, x=10.0),))
        broken = ScenarioBundle(
            scenario_id=bundle.scenario_id,
            timestamps_seconds=bundle.timestamps_seconds,
            current_time_index=bundle.current_time_index,
            sdc_track_index=bundle.sdc_track_index,
            objects_of_interest=bundle.objects_of_interest,
            prediction_targets=bundle.prediction_targets,
            frames=tuple(frames),
            map_features=bundle.map_features,
            source=bundle.source,
            has_lidar_data=bundle.has_lidar_data,
        )

        with self.assertRaisesRegex(AlignmentError, "sdc_track_index"):
            ScenarioAlignment().align(broken)

    def test_rule_parser_accepts_sdc_subjects(self):
        from trigger_engine.rules.parser import RuleParser

        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: sdc_agent_rule
    subject: sdc_agent
    when:
      all:
        - operator: predicate.sdc_agent_true
    emit:
      tag: sdc_agent_rule

  - id: sdc_pair_rule
    subject: sdc_pair
    when:
      all:
        - operator: predicate.sdc_pair_true
    emit:
      tag: sdc_pair_rule
"""
        )

        self.assertEqual(rule_set.rules[0].subject_type, "sdc_agent")
        self.assertEqual(rule_set.rules[1].subject_type, "sdc_pair")

    def test_rule_engine_generates_only_sdc_agent_subject(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysSdcAgentTrueOperator())
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: sdc_agent_rule
    subject: sdc_agent
    when:
      all:
        - operator: predicate.sdc_agent_true
    emit:
      tag: sdc_agent_rule
"""
        )

        events = RuleEngine(registry).evaluate(rule_set, aligned_context())

        self.assertEqual([event.subject_id for event in events], [100, 100])
        self.assertEqual(events[0].metadata["ego_id"], 100)
        self.assertEqual(events[0].metadata["ego_role"], "sdc")

    def test_rule_engine_generates_only_sdc_to_target_pairs(self):
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysSdcPairTrueOperator())
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: sdc_pair_rule
    subject: sdc_pair
    when:
      all:
        - operator: predicate.sdc_pair_true
    emit:
      tag: sdc_pair_rule
      intent: review
"""
        )

        events = RuleEngine(registry).evaluate(rule_set, aligned_context())

        self.assertEqual([event.subject_id for event in events], ["100:200", "100:200", "100:300"])
        self.assertNotIn("200:100", [event.subject_id for event in events])
        self.assertEqual(events[0].metadata["pair_mode"], "sdc")
        self.assertEqual(events[0].metadata["ego_id"], 100)
        self.assertEqual(events[0].metadata["ego_role"], "sdc")
        self.assertEqual(events[0].metadata["target_id"], 200)
        self.assertEqual(events[0].metadata["target_role"], "interactive_agent")

    def test_only_current_frame_rule_skips_history_before_subject_generation(self):
        from trigger_engine.engine.subjects import SubjectCache
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysSdcPairTrueOperator())
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: current_sdc_pair_rule
    subject: sdc_pair
    when:
      all:
        - operator: predicate.sdc_pair_true
          args:
            only_current_frame: true
    emit:
      tag: current_sdc_pair_rule
      intent: review
"""
        )
        cache = SubjectCache()

        events = RuleEngine(registry).evaluate(
            rule_set,
            aligned_context(),
            subject_cache=cache,
        )

        self.assertEqual([event.frame_index for event in events], [1, 1])
        self.assertEqual([event.subject_id for event in events], ["100:200", "100:300"])

    def test_rule_engine_rejects_sdc_subjects_without_sdc_identity(self):
        from dataclasses import replace
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.rules.engine import RuleEngine, RuleEngineError
        from trigger_engine.rules.parser import RuleParser

        registry = OperatorRegistry()
        registry.register(AlwaysSdcPairTrueOperator())
        rule_set = RuleParser().parse_yaml(
            """
rules:
  - id: sdc_pair_rule
    subject: sdc_pair
    when:
      all:
        - operator: predicate.sdc_pair_true
    emit:
      tag: sdc_pair_rule
"""
        )
        context = replace(aligned_context(), sdc_track_id=None)

        with self.assertRaisesRegex(RuleEngineError, "sdc"):
            RuleEngine(registry).evaluate(rule_set, context)


if __name__ == "__main__":
    unittest.main()
