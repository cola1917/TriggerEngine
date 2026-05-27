import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, MapFeature, Point3D


def agent(track_id, step, x=0.0, y=0.0, vx=0.0, vy=0.0, heading=0.0, object_type="vehicle"):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type=object_type,
        timestamp_seconds=step * 0.1,
        center=Point3D(x, y, 0.0),
        velocity_x=vx,
        velocity_y=vy,
        heading=heading,
        length=4.0 if object_type == "vehicle" else 1.0,
        width=1.8 if object_type == "vehicle" else 0.8,
        height=1.5,
        valid=True,
    )


def aligned_frame(step, agents, map_available=False):
    modalities = {"agents", "valid_agents"}
    if map_available:
        modalities.add("map")
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-v2",
            step_index=step,
            timestamp_seconds=step * 0.1,
            phase="current" if step == 10 else "history",
            agent_states=tuple(agents),
            traffic_lights=(),
        ),
        visibility="current" if step == 10 else "observed",
        available_modalities=frozenset(modalities),
    )


def straight_lane(lane_id, y):
    return MapFeature(
        feature_id=lane_id,
        feature_type="lane",
        polyline=(Point3D(-20.0, y, 0.0), Point3D(60.0, y, 0.0)),
        polygon=(),
        properties={},
    )


def context(frames, map_features=None):
    return AlignmentContext(
        scenario_id="scenario-v2",
        watermark=Watermark("scenario-v2", frames[-1].frame.step_index, frames[-1].frame.timestamp_seconds),
        observed_frames=tuple(frames[:-1]),
        current_frame=frames[-1],
        future_frames=(),
        input_frames=tuple(frames),
        source="unit",
        map_features=map_features or {},
        sdc_track_index=1,
        sdc_track_id=1,
    )


def engine_result(ctx):
    from trigger_engine.engine.registry import RuleRegistry
    from trigger_engine.engine.trigger_engine import TriggerEngine
    from trigger_engine.operators.registry import OperatorRegistry
    from trigger_engine.scenarios.classic import register_classic_scenario_pack

    operators = OperatorRegistry()
    rules = RuleRegistry(operator_registry=operators)
    register_classic_scenario_pack(operators, rules)
    return TriggerEngine(operators, rules).evaluate(ctx)


class V2TriggerRulesContractTests(unittest.TestCase):
    def test_classic_pack_emits_sdc_hard_braking_with_front_target(self):
        past = aligned_frame(
            0,
            (
                agent(1, 0, x=0.0, vx=12.0),
                agent(2, 0, x=25.0, vx=8.0),
            ),
        )
        current = aligned_frame(
            10,
            (
                agent(1, 10, x=8.0, vx=7.0),
                agent(2, 10, x=24.0, vx=6.0),
            ),
        )
        result = engine_result(context((past, current)))
        reviews = [event for event in result.events if event.metadata.get("intent") == "review"]

        self.assertIn("sdc_hard_braking", {event.tag_name for event in reviews})
        hard_brake = next(event for event in reviews if event.tag_name == "sdc_hard_braking")
        self.assertEqual(hard_brake.subject_type, "sdc_pair")
        self.assertEqual(hard_brake.subject_id, "1:2")

    def test_classic_pack_emits_vru_close_interaction_for_pedestrian_target(self):
        current = aligned_frame(
            10,
            (
                agent(1, 10, x=0.0, y=0.0, vx=5.0, object_type="vehicle"),
                agent(20, 10, x=8.0, y=2.0, vx=0.0, vy=0.5, object_type="pedestrian"),
            ),
        )
        result = engine_result(context((current,)))
        reviews = [event for event in result.events if event.metadata.get("intent") == "review"]

        self.assertIn("vru_close_interaction", {event.tag_name for event in reviews})
        vru = next(event for event in reviews if event.tag_name == "vru_close_interaction")
        self.assertEqual(vru.subject_id, "1:20")

    def test_vru_close_interaction_rejects_wide_slow_pedestrian(self):
        current = aligned_frame(
            10,
            (
                agent(1, 10, x=0.0, y=0.0, vx=3.0, object_type="vehicle"),
                agent(20, 10, x=8.0, y=3.8, vx=2.7, object_type="pedestrian"),
            ),
        )
        result = engine_result(context((current,)))
        reviews = [event for event in result.events if event.metadata.get("intent") == "review"]

        self.assertNotIn("vru_close_interaction", {event.tag_name for event in reviews})

    def test_vru_close_interaction_keeps_wider_cyclist_with_strong_closing(self):
        current = aligned_frame(
            10,
            (
                agent(1, 10, x=0.0, y=0.0, vx=7.0, object_type="vehicle"),
                agent(20, 10, x=10.0, y=4.5, vx=4.0, object_type="cyclist"),
            ),
        )
        result = engine_result(context((current,)))
        reviews = [event for event in result.events if event.metadata.get("intent") == "review"]

        self.assertIn("vru_close_interaction", {event.tag_name for event in reviews})

    def test_vru_close_interaction_rejects_far_behind_target(self):
        current = aligned_frame(
            10,
            (
                agent(1, 10, x=0.0, y=0.0, vx=5.0, object_type="vehicle"),
                agent(20, 10, x=-4.0, y=1.0, vx=0.0, object_type="pedestrian"),
            ),
        )
        result = engine_result(context((current,)))
        reviews = [event for event in result.events if event.metadata.get("intent") == "review"]

        self.assertNotIn("vru_close_interaction", {event.tag_name for event in reviews})

    def test_classic_pack_emits_lane_change_conflict(self):
        frames = (
            aligned_frame(
                0,
                (
                    agent(1, 0, x=0.0, y=0.0, vx=8.0),
                    agent(2, 0, x=15.0, y=3.5, vx=4.0),
                ),
                map_available=True,
            ),
            aligned_frame(
                5,
                (
                    agent(1, 5, x=4.0, y=1.8, vx=8.0),
                    agent(2, 5, x=17.0, y=3.5, vx=4.0),
                ),
                map_available=True,
            ),
            aligned_frame(
                10,
                (
                    agent(1, 10, x=8.0, y=3.5, vx=8.0),
                    agent(2, 10, x=18.0, y=3.5, vx=4.0),
                ),
                map_available=True,
            ),
        )
        ctx = context(frames, map_features={1: straight_lane(1, 0.0), 2: straight_lane(2, 3.5)})
        result = engine_result(ctx)
        reviews = [event for event in result.events if event.metadata.get("intent") == "review"]

        self.assertIn("lane_change_conflict", {event.tag_name for event in reviews})
        conflict = next(event for event in reviews if event.tag_name == "lane_change_conflict")
        self.assertEqual(conflict.subject_id, "1:2")

    def test_lane_change_conflict_requires_moving_target(self):
        frames = (
            aligned_frame(
                0,
                (
                    agent(1, 0, x=0.0, y=0.0, vx=8.0),
                    agent(2, 0, x=15.0, y=3.5, vx=0.0),
                ),
                map_available=True,
            ),
            aligned_frame(
                5,
                (
                    agent(1, 5, x=4.0, y=1.8, vx=8.0),
                    agent(2, 5, x=15.0, y=3.5, vx=0.0),
                ),
                map_available=True,
            ),
            aligned_frame(
                10,
                (
                    agent(1, 10, x=8.0, y=3.5, vx=8.0),
                    agent(2, 10, x=15.0, y=3.5, vx=0.0),
                ),
                map_available=True,
            ),
        )
        ctx = context(frames, map_features={1: straight_lane(1, 0.0), 2: straight_lane(2, 3.5)})
        result = engine_result(ctx)
        reviews = [event for event in result.events if event.metadata.get("intent") == "review"]

        self.assertNotIn("lane_change_conflict", {event.tag_name for event in reviews})


if __name__ == "__main__":
    unittest.main()
