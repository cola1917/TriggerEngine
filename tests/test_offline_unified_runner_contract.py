import tempfile
import unittest
from pathlib import Path

from trigger_engine.data.frames import AgentState, Frame, Point3D, ScenarioBundle
from trigger_engine.engine.trigger_engine import EngineResult, EngineStats
from trigger_engine.rules.events import TagEvent


def agent(track_id=1):
    return AgentState(
        track_id=track_id,
        track_index=track_id if isinstance(track_id, int) else 0,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(0.0, 0.0, 0.0),
        velocity_x=0.0,
        velocity_y=0.0,
        heading=0.0,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def bundle(name="unit-scene"):
    frames = tuple(
        Frame(
            scenario_id=name,
            step_index=index,
            timestamp_seconds=index * 0.1,
            phase="current" if index == 1 else "history",
            agent_states=(agent(1),),
            traffic_lights=(),
        )
        for index in range(2)
    )
    return ScenarioBundle(
        scenario_id=name,
        timestamps_seconds=(0.0, 0.1),
        current_time_index=1,
        sdc_track_index=1,
        objects_of_interest=(),
        prediction_targets=(),
        frames=frames,
        map_features={},
        source="unit-source",
        has_lidar_data=False,
    )


class FakeSource:
    source_type = "fake"

    def __init__(self):
        self.loaded_units = []

    def list_units(self):
        return ["scene-b", "scene-a"]

    def load_bundle(self, unit_id):
        self.loaded_units.append(unit_id)
        return bundle(unit_id)

    def payload_context(self, scenario_bundle, *, future_steps):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment

        return ScenarioAlignment().align(
            scenario_bundle,
            history_steps=len(scenario_bundle.frames) - 1,
            future_steps=future_steps,
        )

    def payload_name(self, unit_id, scenario_bundle):
        return f"fake_{unit_id}.json"


class StreamingFakeSource(FakeSource):
    configured_for_payloads = None

    def configure_for_run(self, config):
        self.configured_for_payloads = config.write_payloads

    def iter_bundles(self):
        yield "stream-a", bundle("stream-a")
        yield "stream-b", bundle("stream-b")

    def list_units(self):
        raise AssertionError("streaming source should not list units")

    def load_bundle(self, unit_id):
        raise AssertionError("streaming source should not reload units")


class StreamingTimedFakeSource(FakeSource):
    def iter_bundles(self):
        yield "timed-a", bundle("timed-a"), {
            "source_decode_seconds": 1.25,
            "source_adapter_seconds": 2.5,
            "source_load_seconds": 3.75,
        }

    def list_units(self):
        raise AssertionError("streaming source should not list units")

    def load_bundle(self, unit_id):
        raise AssertionError("streaming source should not reload units")


class FakeEngine:
    def evaluate_offline_scene(self, scenario_bundle):
        events = (
            TagEvent(
                scenario_bundle.scenario_id,
                scenario_bundle.source,
                1,
                0.1,
                "sdc_hard_braking",
                "sdc_pair",
                "ego:target",
                True,
                "sdc_hard_braking",
                {"intent": "review", "evaluation_mode": "offline_full_scene"},
            ),
        )
        return EngineResult(
            scenario_id=scenario_bundle.scenario_id,
            source=scenario_bundle.source,
            plan_id="unit",
            events=events,
            stats=EngineStats(2, 0, 1, 0, 1),
            diagnostics=(),
        )


class UnifiedOfflineRunnerContractTests(unittest.TestCase):
    def test_artifact_paths_are_source_agnostic(self):
        from trigger_engine.offline.artifacts import offline_artifact_paths

        paths = offline_artifact_paths(Path("outputs") / "offline" / "fake-run")

        self.assertEqual(paths.summary, Path("outputs") / "offline" / "fake-run" / "summary.json")
        self.assertEqual(paths.payload_dir, Path("outputs") / "offline" / "fake-run" / "payloads")
        self.assertEqual(paths.review_html, Path("outputs") / "offline" / "fake-run" / "review.html")
        self.assertEqual(paths.viewer_dir, Path("outputs") / "offline" / "fake-run" / "viewers")

    def test_unified_runner_evaluates_source_units_and_writes_payloads(self):
        from trigger_engine.offline.runner import OfflineRunConfig, run_offline_source

        source = FakeSource()
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_offline_source(
                source,
                engine=FakeEngine(),
                config=OfflineRunConfig(
                    run_dir=Path(tmp),
                    batch_size=5,
                    workers=1,
                    future_steps=0,
                    map_feature_limit=10,
                    map_crop_margin_m=0.0,
                ),
            )

            self.assertEqual(source.loaded_units, ["scene-b", "scene-a"])
            self.assertEqual(summary["source_type"], "fake")
            self.assertEqual(summary["total_scenarios"], 2)
            self.assertEqual(summary["review_scenarios"], 2)
            self.assertEqual(summary["review_event_counts"], {"sdc_hard_braking": 2})
            self.assertEqual(summary["rule_profile"], [])
            self.assertEqual(len(summary["payload_outputs"]), 2)
            self.assertNotIn("rule_profile", summary["scenario_summaries"][0])
            for output in summary["payload_outputs"]:
                self.assertTrue(Path(output).exists())
            self.assertTrue((Path(tmp) / "summary.json").exists())
            self.assertTrue((Path(tmp) / "review.html").exists())

    def test_unified_runner_streams_source_bundles_when_available(self):
        from trigger_engine.offline.runner import OfflineRunConfig, run_offline_source

        with tempfile.TemporaryDirectory() as tmp:
            source = StreamingFakeSource()
            summary = run_offline_source(
                source,
                engine=FakeEngine(),
                config=OfflineRunConfig(run_dir=Path(tmp), write_payloads=False),
            )

            self.assertEqual(summary["total_scenarios"], 2)
            self.assertFalse(source.configured_for_payloads)
            self.assertEqual(
                [item["unit_id"] for item in summary["scenario_summaries"]],
                ["stream-a", "stream-b"],
            )

    def test_unified_runner_merges_streaming_source_timings(self):
        from trigger_engine.offline.runner import OfflineRunConfig, run_offline_source

        with tempfile.TemporaryDirectory() as tmp:
            summary = run_offline_source(
                StreamingTimedFakeSource(),
                engine=FakeEngine(),
                config=OfflineRunConfig(run_dir=Path(tmp), write_payloads=False),
            )

            self.assertEqual(summary["total_scenarios"], 1)
            self.assertEqual(summary["timings"]["source_decode_seconds"], 1.25)
            self.assertEqual(summary["timings"]["source_adapter_seconds"], 2.5)
            self.assertEqual(summary["timings"]["source_load_seconds"], 3.75)
            self.assertEqual(
                summary["scenario_summaries"][0]["timings"]["source_load_seconds"],
                3.75,
            )


if __name__ == "__main__":
    unittest.main()
