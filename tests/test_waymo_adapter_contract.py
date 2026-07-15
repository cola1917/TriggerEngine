import unittest
from types import SimpleNamespace


def point(x, y, z=0.0):
    return SimpleNamespace(x=x, y=y, z=z)


class MapFeatureProto(SimpleNamespace):
    def WhichOneof(self, _name):
        return self.feature_type


class LaneStateProto(SimpleNamespace):
    def HasField(self, name):
        return name == "stop_point" and getattr(self, "stop_point", None) is not None


def make_fake_scenario():
    valid_state_0 = SimpleNamespace(
        center_x=0.0,
        center_y=1.0,
        center_z=0.0,
        velocity_x=2.0,
        velocity_y=3.0,
        heading=0.1,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )
    invalid_state_1 = SimpleNamespace(
        center_x=10.0,
        center_y=11.0,
        center_z=0.0,
        velocity_x=0.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=False,
    )
    track_vehicle = SimpleNamespace(
        id=100,
        object_type=1,
        states=(valid_state_0, invalid_state_1, valid_state_0),
    )
    track_pedestrian = SimpleNamespace(
        id=200,
        object_type=2,
        states=(valid_state_0, valid_state_0, valid_state_0),
    )
    lane = SimpleNamespace(
        type=2,
        speed_limit_mph=35.0,
        interpolating=False,
        polyline=(point(0.0, 0.0), point(1.0, 1.0)),
        entry_lanes=(1,),
        exit_lanes=(2,),
        left_boundaries=(),
        right_boundaries=(),
        left_neighbors=(),
        right_neighbors=(),
    )
    map_feature = MapFeatureProto(id=7, feature_type="lane", lane=lane)
    dynamic_state = SimpleNamespace(
        lane_states=(
            LaneStateProto(lane=7, state=6, stop_point=point(5.0, 6.0)),
        )
    )

    return SimpleNamespace(
        scenario_id="scenario-contract",
        timestamps_seconds=(0.0, 0.1, 0.2),
        current_time_index=1,
        tracks=(track_vehicle, track_pedestrian),
        dynamic_map_states=(dynamic_state, dynamic_state, dynamic_state),
        map_features=(map_feature,),
        sdc_track_index=0,
        objects_of_interest=(200,),
        tracks_to_predict=(SimpleNamespace(track_index=1, difficulty=1),),
        compressed_frame_laser_data=(),
    )


def make_map_feature(feature_id, feature_type, payload):
    return MapFeatureProto(id=feature_id, feature_type=feature_type, **{feature_type: payload})


class WaymoAdapterContractTests(unittest.TestCase):
    def test_adapter_converts_waymo_scenario_into_internal_bundle(self):
        from trigger_engine.data.adapters import WaymoScenarioAdapter

        bundle = WaymoScenarioAdapter().from_proto(make_fake_scenario(), source="fake")

        self.assertEqual(bundle.scenario_id, "scenario-contract")
        self.assertEqual(bundle.timestamps_seconds, (0.0, 0.1, 0.2))
        self.assertEqual([frame.phase for frame in bundle.frames], ["history", "current", "future"])
        self.assertEqual(len(bundle.frames[1].agent_states), 2)
        self.assertEqual(bundle.frames[1].agent_states[0].object_type, "vehicle")
        self.assertFalse(bundle.frames[1].agent_states[0].valid)
        self.assertEqual(bundle.frames[1].traffic_lights[0].state, "go")
        self.assertEqual(bundle.map_features[7].feature_type, "lane")
        self.assertEqual(bundle.prediction_targets[0].track_id, 200)
        self.assertFalse(bundle.has_lidar_data)

    def test_adapter_rejects_track_state_length_mismatch(self):
        from trigger_engine.data.adapters import DataAdapterError, WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.tracks[0].states = scenario.tracks[0].states[:2]

        with self.assertRaisesRegex(DataAdapterError, "tracks\\[0\\].states"):
            WaymoScenarioAdapter().from_proto(scenario)

    def test_adapter_rejects_invalid_current_time_index(self):
        from trigger_engine.data.adapters import DataAdapterError, WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.current_time_index = 99

        with self.assertRaisesRegex(DataAdapterError, "current_time_index"):
            WaymoScenarioAdapter().from_proto(scenario)

    def test_adapter_converts_all_supported_map_feature_types(self):
        from trigger_engine.data.adapters import WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.map_features = (
            scenario.map_features[0],
            make_map_feature(
                8,
                "road_line",
                SimpleNamespace(type=2, polyline=(point(0.0, 0.0), point(1.0, 0.0))),
            ),
            make_map_feature(
                9,
                "road_edge",
                SimpleNamespace(type=1, polyline=(point(0.0, 1.0), point(1.0, 1.0))),
            ),
            make_map_feature(
                10,
                "crosswalk",
                SimpleNamespace(polygon=(point(0.0, 0.0), point(1.0, 0.0), point(1.0, 1.0))),
            ),
            make_map_feature(
                11,
                "speed_bump",
                SimpleNamespace(polygon=(point(2.0, 0.0), point(3.0, 0.0), point(3.0, 1.0))),
            ),
            make_map_feature(
                12,
                "stop_sign",
                SimpleNamespace(position=point(5.0, 5.0), lane=(7,)),
            ),
            make_map_feature(
                13,
                "driveway",
                SimpleNamespace(polygon=(point(4.0, 0.0), point(5.0, 0.0), point(5.0, 1.0))),
            ),
        )

        bundle = WaymoScenarioAdapter().from_proto(scenario)

        self.assertEqual(bundle.map_features[8].feature_type, "road_line")
        self.assertEqual(bundle.map_features[8].properties["road_line_type"], "solid_single_white")
        self.assertEqual(bundle.map_features[9].feature_type, "road_edge")
        self.assertEqual(bundle.map_features[10].feature_type, "crosswalk")
        self.assertEqual(len(bundle.map_features[11].polygon), 3)
        self.assertEqual(bundle.map_features[12].properties["lane_ids"], (7,))
        self.assertEqual(bundle.map_features[13].feature_type, "driveway")

    def test_adapter_can_skip_visual_map_features_for_rule_only_runs(self):
        from trigger_engine.data.adapters import WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.map_features = (
            scenario.map_features[0],
            make_map_feature(
                8,
                "road_line",
                SimpleNamespace(type=2, polyline=(point(0.0, 0.0), point(1.0, 0.0))),
            ),
            make_map_feature(
                9,
                "crosswalk",
                SimpleNamespace(polygon=(point(0.0, 0.0), point(1.0, 0.0), point(1.0, 1.0))),
            ),
            make_map_feature(
                10,
                "stop_sign",
                SimpleNamespace(position=point(5.0, 5.0), lane=(7,)),
            ),
        )

        bundle = WaymoScenarioAdapter(include_visual_map_features=False).from_proto(scenario)

        self.assertEqual(set(bundle.map_features), {7, 10})
        self.assertEqual(bundle.map_features[7].feature_type, "lane")
        self.assertEqual(bundle.map_features[10].feature_type, "stop_sign")

    def test_adapter_rejects_dynamic_map_state_length_mismatch(self):
        from trigger_engine.data.adapters import DataAdapterError, WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.dynamic_map_states = scenario.dynamic_map_states[:2]

        with self.assertRaisesRegex(DataAdapterError, "dynamic_map_states"):
            WaymoScenarioAdapter().from_proto(scenario)

    def test_adapter_rejects_invalid_sdc_track_index(self):
        from trigger_engine.data.adapters import DataAdapterError, WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.sdc_track_index = 99

        with self.assertRaisesRegex(DataAdapterError, "sdc_track_index"):
            WaymoScenarioAdapter().from_proto(scenario)

    def test_adapter_rejects_invalid_prediction_track_index(self):
        from trigger_engine.data.adapters import DataAdapterError, WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.tracks_to_predict = (SimpleNamespace(track_index=99, difficulty=1),)

        with self.assertRaisesRegex(DataAdapterError, "tracks_to_predict\\[0\\].track_index"):
            WaymoScenarioAdapter().from_proto(scenario)

    def test_adapter_rejects_empty_timeline(self):
        from trigger_engine.data.adapters import DataAdapterError, WaymoScenarioAdapter

        scenario = make_fake_scenario()
        scenario.timestamps_seconds = ()

        with self.assertRaisesRegex(DataAdapterError, "timestamps_seconds"):
            WaymoScenarioAdapter().from_proto(scenario)


if __name__ == "__main__":
    unittest.main()
