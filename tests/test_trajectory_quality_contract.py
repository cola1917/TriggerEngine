import unittest

from trigger_engine.data.frames import (
    AgentState,
    Frame,
    Point3D,
    ScenarioBundle,
)


def agent(track_id, step, x, y=0.0, vx=0.0, vy=0.0, heading=0.0, valid=True):
    return AgentState(
        track_id=track_id,
        track_index=0,
        object_type="vehicle",
        timestamp_seconds=step * 0.5,
        center=Point3D(x, y, 0.0),
        velocity_x=vx,
        velocity_y=vy,
        heading=heading,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=valid,
    )


def frame(step, *agents):
    return Frame(
        scenario_id="scenario-quality",
        step_index=step,
        timestamp_seconds=step * 0.5,
        phase="current" if step == 2 else "history",
        agent_states=tuple(agents),
        traffic_lights=(),
    )


def bundle_with_jump():
    frames = (
        frame(0, agent(1, 0, 0.0, vx=1.0)),
        frame(1, agent(1, 1, 100.0, vx=1.0)),
        frame(2, agent(1, 2, 101.0, vx=1.0)),
    )
    return ScenarioBundle(
        scenario_id="scenario-quality",
        timestamps_seconds=(0.0, 0.5, 1.0),
        current_time_index=2,
        sdc_track_index=0,
        objects_of_interest=(),
        prediction_targets=(),
        frames=frames,
        map_features={},
        source="unit",
        has_lidar_data=False,
    )


class TrajectoryQualityContractTests(unittest.TestCase):
    def test_quality_issue_dataclass_is_available(self):
        from dataclasses import is_dataclass
        from trigger_engine.data.quality import TrajectoryQualityIssue

        self.assertTrue(is_dataclass(TrajectoryQualityIssue))

    def test_annotator_marks_jump_without_mutating_trajectory_values(self):
        from trigger_engine.data.quality import (
            TrajectoryQualityAnnotator,
            TrajectoryQualityConfig,
        )

        original = bundle_with_jump()
        annotated = TrajectoryQualityAnnotator(
            TrajectoryQualityConfig(max_implied_speed_mps=50.0)
        ).annotate(original)

        self.assertEqual(annotated.frames, original.frames)
        self.assertEqual(annotated.timestamps_seconds, original.timestamps_seconds)
        self.assertEqual(len(annotated.quality_issues), 1)
        issue = annotated.quality_issues[0]
        self.assertEqual(issue.issue_type, "jump_speed")
        self.assertEqual(issue.track_id, 1)
        self.assertEqual(issue.frame_index, 1)
        self.assertGreater(issue.value, issue.threshold)
        self.assertEqual(issue.metadata["previous_frame_index"], 0)

    def test_annotator_ignores_invalid_states_and_keeps_bundle_shape(self):
        from trigger_engine.data.quality import TrajectoryQualityAnnotator

        original = bundle_with_jump()
        broken_frames = list(original.frames)
        broken_frames[1] = frame(1, agent(1, 1, 100.0, valid=False))
        original = ScenarioBundle(
            scenario_id=original.scenario_id,
            timestamps_seconds=original.timestamps_seconds,
            current_time_index=original.current_time_index,
            sdc_track_index=original.sdc_track_index,
            objects_of_interest=original.objects_of_interest,
            prediction_targets=original.prediction_targets,
            frames=tuple(broken_frames),
            map_features=original.map_features,
            source=original.source,
            has_lidar_data=original.has_lidar_data,
        )

        annotated = TrajectoryQualityAnnotator().annotate(original)

        self.assertEqual(annotated.frames, original.frames)
        self.assertEqual(annotated.quality_issues, ())


if __name__ == "__main__":
    unittest.main()
