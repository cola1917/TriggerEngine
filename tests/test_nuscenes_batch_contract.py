import tempfile
import unittest
from pathlib import Path

from trigger_engine.engine.trigger_engine import EngineStats
from trigger_engine.rules.events import TagEvent


class NuScenesBatchContractTests(unittest.TestCase):
    def test_offline_artifact_paths_keep_payload_and_review_outputs_under_run_dir(self):
        from tools.run_nuscenes_batch import offline_artifact_paths

        paths = offline_artifact_paths(Path("outputs") / "offline" / "nuscenes-mini")

        self.assertEqual(paths.output, Path("outputs") / "offline" / "nuscenes-mini" / "summary.json")
        self.assertEqual(paths.payload_dir, Path("outputs") / "offline" / "nuscenes-mini" / "payloads")
        self.assertEqual(paths.view_output, Path("outputs") / "offline" / "nuscenes-mini" / "review.html")
        self.assertEqual(paths.viewer_dir, Path("outputs") / "offline" / "nuscenes-mini" / "viewers")

    def test_offline_artifact_paths_allow_explicit_overrides(self):
        from tools.run_nuscenes_batch import offline_artifact_paths

        paths = offline_artifact_paths(
            Path("run"),
            output=Path("custom") / "summary.json",
            payload_dir=Path("custom") / "payloads",
            view_output=Path("custom") / "review.html",
            viewer_dir=Path("custom") / "viewers",
        )

        self.assertEqual(paths.output, Path("custom") / "summary.json")
        self.assertEqual(paths.payload_dir, Path("custom") / "payloads")
        self.assertEqual(paths.view_output, Path("custom") / "review.html")
        self.assertEqual(paths.viewer_dir, Path("custom") / "viewers")

    def test_merge_scene_summaries_counts_reviews_and_payloads(self):
        from tools.run_nuscenes_batch import merge_scene_summaries

        summary = merge_scene_summaries(
            [
                {
                    "scene": "scene-a",
                    "scenario_id": "a",
                    "events": 2,
                    "review_events": 1,
                    "review_event_counts": {"vru_close_interaction": 1},
                    "payload_output": "payloads/a.json",
                    "seconds": 1.0,
                },
                {
                    "scene": "scene-b",
                    "scenario_id": "b",
                    "events": 3,
                    "review_events": 2,
                    "review_event_counts": {"sdc_hard_braking": 2},
                    "payload_output": None,
                    "seconds": 2.0,
                },
            ],
            elapsed=4.0,
            batch_size=5,
        )

        self.assertEqual(summary["total_scenes"], 2)
        self.assertEqual(summary["review_scenes"], 2)
        self.assertEqual(summary["review_events"], 3)
        self.assertEqual(
            summary["review_event_counts"],
            {"sdc_hard_braking": 2, "vru_close_interaction": 1},
        )
        self.assertEqual(summary["payload_outputs"], ["payloads/a.json"])
        self.assertEqual(summary["batch_size"], 5)

    def test_write_nuscenes_scene_payload_uses_compacted_events(self):
        from tools.run_nuscenes_batch import write_nuscenes_scene_payload

        class Context:
            scenario_id = "scene"
            source = "unit"
            map_features = {}
            observed_frames = ()
            future_frames = ()
            input_frames = ()

        events = (
            TagEvent("scene", "unit", 7, 0.7, "sdc_hard_braking", "sdc_pair", "ego:a", True, "r", {"intent": "review"}),
            TagEvent("scene", "unit", 7, 0.7, "sdc_hard_braking", "sdc_pair", "ego:b", True, "r", {"intent": "review"}),
        )

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "payload.json"
            write_nuscenes_scene_payload(
                Context(),
                events,
                EngineStats(1, 0, 1, 0, 2),
                output,
            )

            text = output.read_text(encoding="utf-8")
            self.assertIn('"review_event_groups_by_tag"', text)
            self.assertIn('"suppressed_event_count": 1', text)


if __name__ == "__main__":
    unittest.main()
