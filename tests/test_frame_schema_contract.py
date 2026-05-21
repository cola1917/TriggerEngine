import unittest
from dataclasses import is_dataclass


class FrameSchemaContractTests(unittest.TestCase):
    def test_core_frame_dataclasses_are_available(self):
        from trigger_engine.data.frames import (
            AgentState,
            Frame,
            MapFeature,
            Point3D,
            PredictionTarget,
            ScenarioBundle,
            TrafficLightState,
        )

        for cls in (
            AgentState,
            Frame,
            MapFeature,
            Point3D,
            PredictionTarget,
            ScenarioBundle,
            TrafficLightState,
        ):
            self.assertTrue(is_dataclass(cls), f"{cls.__name__} must be a dataclass")

    def test_frame_schema_keeps_time_slice_data_aligned(self):
        from trigger_engine.data.frames import AgentState, Frame, Point3D, TrafficLightState

        agent_state = AgentState(
            track_id=100,
            track_index=0,
            object_type="vehicle",
            timestamp_seconds=1.0,
            center=Point3D(1.0, 2.0, 0.5),
            velocity_x=3.0,
            velocity_y=4.0,
            heading=0.1,
            length=4.5,
            width=1.8,
            height=1.6,
            valid=False,
        )
        traffic_light = TrafficLightState(
            lane_id=55,
            state="go",
            stop_point=Point3D(9.0, 8.0, 0.0),
        )

        frame = Frame(
            scenario_id="scenario-a",
            step_index=2,
            timestamp_seconds=1.0,
            phase="current",
            agent_states=(agent_state,),
            traffic_lights=(traffic_light,),
        )

        self.assertEqual(frame.agent_states[0].track_id, 100)
        self.assertFalse(frame.agent_states[0].valid)
        self.assertEqual(frame.traffic_lights[0].lane_id, 55)
        self.assertEqual(frame.phase, "current")

    def test_scenario_bundle_exposes_context_indices(self):
        from trigger_engine.data.frames import Frame, MapFeature, PredictionTarget, ScenarioBundle

        frame = Frame(
            scenario_id="scenario-a",
            step_index=0,
            timestamp_seconds=0.0,
            phase="history",
            agent_states=(),
            traffic_lights=(),
        )
        lane = MapFeature(
            feature_id=7,
            feature_type="lane",
            polyline=(),
            polygon=(),
            properties={"speed_limit_mph": 35.0},
        )
        target = PredictionTarget(
            track_index=1,
            track_id=200,
            difficulty="level_1",
            object_type="pedestrian",
        )

        bundle = ScenarioBundle(
            scenario_id="scenario-a",
            timestamps_seconds=(0.0,),
            current_time_index=0,
            sdc_track_index=0,
            objects_of_interest=(200,),
            prediction_targets=(target,),
            frames=(frame,),
            map_features={7: lane},
            source="memory",
            has_lidar_data=False,
        )

        self.assertEqual(bundle.map_features[7].feature_type, "lane")
        self.assertEqual(bundle.prediction_targets[0].track_id, 200)
        self.assertFalse(bundle.has_lidar_data)


if __name__ == "__main__":
    unittest.main()
