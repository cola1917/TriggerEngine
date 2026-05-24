import unittest
from dataclasses import is_dataclass

from trigger_engine.data.frames import (
    AgentState,
    Frame,
    MapFeature,
    Point3D,
    ScenarioBundle,
    TrafficLightState,
)


def agent(track_id, valid=True):
    return AgentState(
        track_id=track_id,
        track_index=track_id,
        object_type="vehicle",
        timestamp_seconds=track_id * 0.1,
        center=Point3D(1.0, 2.0, 0.0),
        velocity_x=3.0,
        velocity_y=4.0,
        heading=0.1,
        length=4.5,
        width=1.8,
        height=1.6,
        valid=valid,
    )


def frame(step_index, phase, agent_states=(), traffic_lights=()):
    return Frame(
        scenario_id="scenario-align",
        step_index=step_index,
        timestamp_seconds=step_index * 0.1,
        phase=phase,
        agent_states=agent_states,
        traffic_lights=traffic_lights,
    )


def make_bundle(current_time_index=2, has_lidar_data=True):
    frames = (
        frame(0, "history", (agent(0),), ()),
        frame(1, "history", (agent(1, valid=False),), ()),
        frame(
            2,
            "current",
            (agent(0), agent(2),),
            (TrafficLightState(lane_id=7, state="go", stop_point=None),),
        ),
        frame(3, "future", (agent(3),), ()),
        frame(4, "future", (), ()),
    )
    return ScenarioBundle(
        scenario_id="scenario-align",
        timestamps_seconds=(0.0, 0.1, 0.2, 0.3, 0.4),
        current_time_index=current_time_index,
        sdc_track_index=0,
        objects_of_interest=(),
        prediction_targets=(),
        frames=frames,
        map_features={
            7: MapFeature(
                feature_id=7,
                feature_type="lane",
                polyline=(),
                polygon=(),
                properties={},
            )
        },
        source="unit-test",
        has_lidar_data=has_lidar_data,
    )


class AlignmentContractTests(unittest.TestCase):
    def test_alignment_context_dataclasses_are_available(self):
        from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark

        for cls in (AlignedFrame, AlignmentContext, Watermark):
            self.assertTrue(is_dataclass(cls), f"{cls.__name__} must be a dataclass")

    def test_align_sets_watermark_and_visibility_without_future_leakage(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        context = ScenarioAlignment().align(make_bundle())

        self.assertEqual(context.scenario_id, "scenario-align")
        self.assertEqual(context.source, "unit-test")
        self.assertEqual(context.watermark.step_index, 2)
        self.assertEqual(context.watermark.timestamp_seconds, 0.2)
        self.assertEqual([item.frame.step_index for item in context.observed_frames], [0, 1])
        self.assertEqual(context.current_frame.frame.step_index, 2)
        self.assertEqual([item.frame.step_index for item in context.future_frames], [3, 4])
        self.assertEqual([item.visibility for item in context.input_frames], ["observed", "observed", "current"])
        self.assertNotIn(3, [item.frame.step_index for item in context.input_frames])

    def test_align_supports_history_and_future_window_limits(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        context = ScenarioAlignment().align(make_bundle(), history_steps=1, future_steps=1)

        self.assertEqual([item.frame.step_index for item in context.observed_frames], [1])
        self.assertEqual([item.frame.step_index for item in context.future_frames], [3])
        self.assertEqual([item.frame.step_index for item in context.input_frames], [1, 2])

    def test_align_supports_zero_length_windows(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        context = ScenarioAlignment().align(make_bundle(), history_steps=0, future_steps=0)

        self.assertEqual(context.observed_frames, ())
        self.assertEqual(context.future_frames, ())
        self.assertEqual([item.frame.step_index for item in context.input_frames], [2])

    def test_aligned_frame_reports_available_modalities(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        context = ScenarioAlignment().align(make_bundle())

        observed_without_valid_agent = context.observed_frames[1]
        current = context.current_frame
        future = context.future_frames[0]
        empty_future = context.future_frames[1]

        self.assertEqual(
            observed_without_valid_agent.available_modalities,
            frozenset({"agents", "map", "lidar"}),
        )
        self.assertEqual(
            current.available_modalities,
            frozenset({"agents", "valid_agents", "traffic_lights", "map", "lidar"}),
        )
        self.assertEqual(
            future.available_modalities,
            frozenset({"agents", "valid_agents", "map"}),
        )
        self.assertEqual(empty_future.available_modalities, frozenset({"map"}))

    def test_align_omits_lidar_modality_when_bundle_has_no_lidar(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        context = ScenarioAlignment().align(make_bundle(has_lidar_data=False))

        self.assertNotIn("lidar", context.current_frame.available_modalities)

    def test_align_rejects_negative_window_limits(self):
        from trigger_engine.alignment.scenario_alignment import AlignmentError, ScenarioAlignment

        with self.assertRaisesRegex(AlignmentError, "history_steps"):
            ScenarioAlignment().align(make_bundle(), history_steps=-1)

        with self.assertRaisesRegex(AlignmentError, "future_steps"):
            ScenarioAlignment().align(make_bundle(), future_steps=-1)

    def test_align_rejects_empty_frames(self):
        from trigger_engine.alignment.scenario_alignment import AlignmentError, ScenarioAlignment

        bundle = make_bundle()
        broken = ScenarioBundle(
            scenario_id=bundle.scenario_id,
            timestamps_seconds=bundle.timestamps_seconds,
            current_time_index=bundle.current_time_index,
            sdc_track_index=bundle.sdc_track_index,
            objects_of_interest=bundle.objects_of_interest,
            prediction_targets=bundle.prediction_targets,
            frames=(),
            map_features=bundle.map_features,
            source=bundle.source,
            has_lidar_data=bundle.has_lidar_data,
        )

        with self.assertRaisesRegex(AlignmentError, "frames"):
            ScenarioAlignment().align(broken)

    def test_align_rejects_invalid_current_time_index(self):
        from trigger_engine.alignment.scenario_alignment import AlignmentError, ScenarioAlignment

        with self.assertRaisesRegex(AlignmentError, "current_time_index"):
            ScenarioAlignment().align(make_bundle(current_time_index=99))

    def test_align_rejects_current_frame_step_mismatch(self):
        from trigger_engine.alignment.scenario_alignment import AlignmentError, ScenarioAlignment

        bundle = make_bundle()
        broken_frames = list(bundle.frames)
        broken_frames[2] = frame(99, "current")
        broken = ScenarioBundle(
            scenario_id=bundle.scenario_id,
            timestamps_seconds=bundle.timestamps_seconds,
            current_time_index=bundle.current_time_index,
            sdc_track_index=bundle.sdc_track_index,
            objects_of_interest=bundle.objects_of_interest,
            prediction_targets=bundle.prediction_targets,
            frames=tuple(broken_frames),
            map_features=bundle.map_features,
            source=bundle.source,
            has_lidar_data=bundle.has_lidar_data,
        )

        with self.assertRaisesRegex(AlignmentError, "step_index"):
            ScenarioAlignment().align(broken)


if __name__ == "__main__":
    unittest.main()
