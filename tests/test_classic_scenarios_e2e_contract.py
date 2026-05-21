import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import AgentState, Frame, Point3D, TrafficLightState


def agent(track_id, x=0.0, y=0.0, vx=0.0, vy=0.0, heading=0.0, object_type="vehicle"):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type=object_type,
        timestamp_seconds=0.0,
        center=Point3D(x, y, 0.0),
        velocity_x=vx,
        velocity_y=vy,
        heading=heading,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def frame(step_index, agents, traffic_lights=()):
    return AlignedFrame(
        frame=Frame(
            scenario_id="scenario-classic",
            step_index=step_index,
            timestamp_seconds=step_index * 0.1,
            phase="current" if step_index == 2 else "history",
            agent_states=agents,
            traffic_lights=traffic_lights,
        ),
        visibility="current" if step_index == 2 else "observed",
        available_modalities=frozenset({"agents", "valid_agents"}),
    )


def make_context():
    stopped = agent(10, x=1.0, y=0.0, vx=0.1)
    ego = agent(20, x=0.0, y=0.0, vx=10.0, heading=0.0)
    front = agent(21, x=10.0, y=0.0, vx=5.0, heading=0.0)
    cutter = agent(22, x=5.0, y=2.0, vx=8.0, vy=-1.0, heading=-0.2)
    red_light = TrafficLightState(lane_id=7, state="stop", stop_point=Point3D(1.0, 0.0, 0.0))
    frames = (
        frame(0, (stopped, ego, front, cutter), (red_light,)),
        frame(1, (stopped, ego, front, cutter), (red_light,)),
        frame(2, (stopped, ego, front, cutter), (red_light,)),
    )
    future = frame(3, (agent(999, vx=0.0),), ())
    return AlignmentContext(
        scenario_id="scenario-classic",
        watermark=Watermark("scenario-classic", 2, 0.2),
        observed_frames=frames[:2],
        current_frame=frames[2],
        future_frames=(future,),
        input_frames=frames,
        source="unit",
    )


class ClassicScenariosE2EContractTests(unittest.TestCase):
    def test_classic_pack_outputs_four_high_value_scenario_families(self):
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import register_classic_scenario_pack

        operators = OperatorRegistry()
        rules = RuleRegistry(operator_registry=operators)
        register_classic_scenario_pack(operators, rules)
        engine = TriggerEngine(operator_registry=operators, rule_registry=rules)

        result = engine.evaluate(make_context())
        tags = {event.tag_name for event in result.events}

        self.assertIn("vehicle_stopped", tags)
        self.assertIn("vehicle_stopped_for_3_frames", tags)
        self.assertIn("low_ttc_pair", tags)
        self.assertIn("persistent_low_ttc_pair", tags)
        self.assertIn("cut_in_candidate", tags)
        self.assertIn("cut_in_developing", tags)
        self.assertIn("vehicle_stopped_at_red", tags)
        self.assertIn("vehicle_still_stopped_at_red", tags)
        self.assertNotIn(999, [event.subject_id for event in result.events])


if __name__ == "__main__":
    unittest.main()
