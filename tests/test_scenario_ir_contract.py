import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from trigger_engine.data.frames import (
    AgentState,
    DataSourceMetadata,
    Frame,
    FrameSampling,
    MapFeature,
    Point3D,
    ScenarioBundle,
)
from trigger_engine.rules.events import TagEvent


SCENE_TOKEN = "a" * 32


def state(track_id, step, *, x=0.0, y=0.0, vx=0.0, vy=0.0, heading=0.0):
    return AgentState(
        track_id=track_id,
        track_index=0 if track_id == "ego" else 1,
        object_type="vehicle",
        timestamp_seconds=float(step),
        center=Point3D(x, y, 0.0),
        velocity_x=vx,
        velocity_y=vy,
        heading=heading,
        length=4.5,
        width=1.9,
        height=1.6,
        valid=True,
    )


def bundle():
    frames = tuple(
        Frame(
            scenario_id=SCENE_TOKEN,
            step_index=step,
            timestamp_seconds=float(step),
            phase="current" if step == 5 else "history",
            agent_states=(
                state("ego", step, x=float(step), vx=5.0),
                state("actor-1", step, x=10.0 + step, y=3.5 - 0.4 * step, vx=4.0, vy=-0.5),
            ),
            traffic_lights=(),
        )
        for step in range(6)
    )
    return ScenarioBundle(
        scenario_id=SCENE_TOKEN,
        timestamps_seconds=tuple(float(step) for step in range(6)),
        current_time_index=5,
        sdc_track_index=0,
        objects_of_interest=(),
        prediction_targets=(),
        frames=frames,
        map_features={
            1: MapFeature(
                feature_id=1,
                feature_type="lane",
                polyline=(Point3D(0.0, 0.0, 0.0), Point3D(20.0, 0.0, 0.0)),
                polygon=(),
                properties={"token": "lane-1"},
            )
        },
        source="data/nuscenes-mini",
        has_lidar_data=True,
        available_capabilities=frozenset({"camera", "lidar", "map"}),
        metadata=DataSourceMetadata(
            source_type="nuscenes",
            dataset_version="v1.0-mini",
            scene_name="scene-test",
            scene_token=SCENE_TOKEN,
            sample_count=6,
            map_location="singapore-onenorth",
            log_token="log-token",
            origin_global_translation=(0.0, 0.0, 0.0),
            origin_global_rotation_wxyz=(1.0, 0.0, 0.0, 0.0),
            origin_global_yaw_rad=0.0,
            coordinate_frame="scene_local_global_axes",
            frame_sampling=FrameSampling(source_hz=2.0),
        ),
    )


def rotated_bundle():
    base = bundle()
    frames = tuple(
        Frame(
            scenario_id=SCENE_TOKEN,
            step_index=step,
            timestamp_seconds=float(step),
            phase="current" if step == 5 else "history",
            agent_states=(
                state(
                    "ego",
                    step,
                    y=float(step),
                    vy=5.0,
                    heading=math.pi / 2.0,
                ),
                state(
                    "actor-1",
                    step,
                    x=-3.0,
                    y=10.0 + step,
                    vy=4.0,
                    heading=math.pi / 2.0,
                ),
            ),
            traffic_lights=(),
        )
        for step in range(6)
    )
    metadata = replace(
        base.metadata,
        origin_global_translation=(10.0, 20.0, 1.0),
        origin_global_rotation_wxyz=(
            math.cos(math.pi / 4.0),
            0.0,
            0.0,
            math.sin(math.pi / 4.0),
        ),
        origin_global_yaw_rad=math.pi / 2.0,
    )
    map_features = {
        1: MapFeature(
            feature_id=1,
            feature_type="lane",
            polyline=(Point3D(0.0, 0.0, 0.0), Point3D(0.0, 20.0, 0.0)),
            polygon=(),
            properties={"token": "lane-1"},
        )
    }
    return replace(base, frames=frames, map_features=map_features, metadata=metadata)


class ScenarioIRContractTests(unittest.TestCase):
    def test_builds_mvp_ir_with_event_and_reconstruction_windows(self):
        from trigger_engine.contracts import ScenarioIRExportConfig, build_scenario_ir

        event = TagEvent(
            scenario_id=SCENE_TOKEN,
            source="unit",
            frame_index=3,
            timestamp_seconds=3.0,
            tag_name="cut_in_risk",
            subject_type="agent",
            subject_id="actor-1",
            value=True,
            rule_id="cut_in",
            metadata={"intent": "review"},
        )

        scenario_ir = build_scenario_ir(
            bundle(),
            trigger_event=event,
            events=(event,),
            config=ScenarioIRExportConfig(
                scenario_type="cut_in",
                event_pre_seconds=1.0,
                event_post_seconds=2.0,
                reconstruction_pre_seconds=5.0,
                reconstruction_post_seconds=5.0,
            ),
        )

        self.assertEqual(scenario_ir["schema_version"], "scenario_ir.v1")
        self.assertEqual(scenario_ir["scenario_id"], SCENE_TOKEN)
        self.assertEqual(scenario_ir["scenario_type"], "cut_in")
        self.assertEqual(scenario_ir["windows"]["event"], {"start_sec": 2.0, "end_sec": 5.0})
        self.assertEqual(scenario_ir["windows"]["reconstruction"], {"start_sec": 0.0, "end_sec": 5.0})
        self.assertEqual(scenario_ir["ego"]["track_id"], "ego")
        self.assertEqual(scenario_ir["actors"][0]["actor_id"], "actor-1")
        self.assertEqual(scenario_ir["actors"][0]["role"], "trigger")
        self.assertEqual(scenario_ir["events"]["trigger"]["tag_name"], "cut_in_risk")
        self.assertIn("map", scenario_ir["sensors"]["available_capabilities"])
        self.assertEqual(scenario_ir["source"]["scene_name"], "scene-test")
        self.assertEqual(scenario_ir["source"]["scene_token"], SCENE_TOKEN)
        self.assertEqual(scenario_ir["map_context"]["location"], "singapore-onenorth")

        reconstruction_required = scenario_ir["data_requirements"]["reconstruction"]["required"]
        self.assertGreaterEqual(
            set(reconstruction_required),
            {"camera_images", "camera_calibration", "ego_pose", "actor_tracks"},
        )
        closed_loop_required = scenario_ir["data_requirements"]["closed_loop"]["required"]
        self.assertGreaterEqual(
            set(closed_loop_required),
            {"ego_initial_state", "actor_initial_states", "map_context"},
        )

        self.assertEqual(
            scenario_ir["risk_metrics"],
            {
                "trigger_time_sec": 3.0,
                "trigger_tag": "cut_in_risk",
                "actor_count": 1,
                "ego_reference_state_count": 6,
            },
        )

        self.assertEqual(
            scenario_ir["dataset_refs"],
            {
                "source": {
                    "dataset": "nuscenes",
                    "root": "data/nuscenes-mini",
                    "scene_id": SCENE_TOKEN,
                    "version": "v1.0-mini",
                    "scene_name": "scene-test",
                    "scene_token": SCENE_TOKEN,
                },
                "sample_refs": {"status": "deferred", "refs": []},
                "index_refs": {"status": "deferred", "refs": []},
            },
        )

    def test_rotates_internal_global_axes_into_first_ego_forward_frame(self):
        from trigger_engine.contracts import build_scenario_ir

        scenario_ir = build_scenario_ir(rotated_bundle())
        frame = scenario_ir["coordinate_frame"]
        self.assertEqual(frame["name"], "scene_local_ego_start")
        self.assertEqual(
            frame["units"],
            {"position": "meter", "time": "second", "yaw": "degree"},
        )
        self.assertEqual(frame["origin_global_translation"], [10.0, 20.0, 1.0])
        self.assertAlmostEqual(frame["origin_global_yaw_deg"], 90.0)

        ego = scenario_ir["ego"]["reference_trajectory"]
        self.assertAlmostEqual(ego[0]["yaw"], 0.0)
        self.assertAlmostEqual(ego[1]["x"], 1.0)
        self.assertAlmostEqual(ego[1]["y"], 0.0)
        self.assertAlmostEqual(ego[1]["vx"], 5.0)
        self.assertAlmostEqual(ego[1]["vy"], 0.0)
        lane = scenario_ir["map_context"]["features"][0]["polyline"]
        self.assertAlmostEqual(lane[1]["x"], 20.0)
        self.assertAlmostEqual(lane[1]["y"], 0.0)

    def test_exports_real_nuscenes_mini_scene_when_available(self):
        from tools.export_scenario_ir import export_nuscenes_scenario_ir

        dataroot = Path("data") / "nuscenes-mini"
        if not dataroot.exists():
            self.skipTest("nuScenes mini data is not available")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scene-1077.v1.json"
            scenario_ir = export_nuscenes_scenario_ir(
                dataroot,
                scene="scene-1077",
                output=output,
                scenario_type="mined_high_value",
            )

            self.assertTrue(output.exists())
            loaded = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(loaded["schema_version"], "scenario_ir.v1")
        self.assertEqual(loaded["scenario_id"], scenario_ir["scenario_id"])
        self.assertEqual(loaded["source"]["dataset"], "nuscenes")
        self.assertEqual(loaded["source"]["scene_name"], "scene-1077")
        self.assertTrue(loaded["source"]["scene_token"])
        self.assertEqual(loaded["scenario_id"], loaded["source"]["scene_token"])
        self.assertNotEqual(loaded["source"]["scene_token"], loaded["source"]["scene_name"])
        self.assertGreater(len(loaded["ego"]["reference_trajectory"]), 0)
        self.assertGreater(len(loaded["actors"]), 0)
        self.assertIn("event", loaded["windows"])


if __name__ == "__main__":
    unittest.main()
