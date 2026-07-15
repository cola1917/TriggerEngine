from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def make_payload(scenario_id: str, events: list[dict], review_indices=None) -> dict:
    if review_indices is None:
        review_indices = [
            i
            for i, event in enumerate(events)
            if event.get("metadata", {}).get("intent") == "review"
        ]
    return {
        "scenario_id": scenario_id,
        "source": f"source-{scenario_id}",
        "plan_id": "classic",
        "watermark": {"frame_index": 2, "timestamp_seconds": 0.2},
        "playback": {
            "history_frame_count": 3,
            "future_frame_count": 0,
            "current_frame_index": 2,
        },
        "frames": [
            {
                "frame_index": 0,
                "timestamp_seconds": 0.0,
                "phase": "history",
                "visibility": {},
                "agents": [],
                "traffic_lights": [],
            }
        ],
        "events": events,
        "review_events": [events[i] for i in review_indices],
        "review_event_indices": review_indices,
        "event_groups": {"primary": review_indices, "supporting": [], "debug": []},
        "map_features": [],
        "view": {
            "scenario_bounds": {
                "min_x": -10.0,
                "max_x": 10.0,
                "min_y": -10.0,
                "max_y": 10.0,
            },
            "event_bounds_by_event_index": {},
        },
        "stats": {"events_emitted": len(events), "rules_evaluated": 1},
        "diagnostics": [],
    }


def event(tag_name: str, frame_index: int, intent: str = "review") -> dict:
    return {
        "tag_name": tag_name,
        "scenario_id": "scenario",
        "frame_index": frame_index,
        "timestamp_seconds": frame_index * 0.1,
        "subject_type": "agent_pair",
        "subject_id": "1:2",
        "rule_name": tag_name,
        "metadata": {"intent": intent},
    }


class ReviewViewerDirectoryIndexContractTests(unittest.TestCase):
    def test_index_includes_only_payloads_with_review_events(self):
        from tools.export_viewer import build_review_payload_index

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "b_debug.json").write_text(
                json.dumps(make_payload("debug", [event("vehicle_stopped", 3, "debug")])),
                encoding="utf-8",
            )
            (root / "a_cut_in.json").write_text(
                json.dumps(make_payload("cut-in", [event("cut_in_risk", 8)])),
                encoding="utf-8",
            )
            (root / "c_low_ttc.json").write_text(
                json.dumps(
                    make_payload(
                        "low-ttc",
                        [
                            event("persistent_low_ttc_pair", 5),
                            event("sdc_repeated_lane_change", 9),
                        ],
                    )
                ),
                encoding="utf-8",
            )

            index = build_review_payload_index(root)

        self.assertEqual(index["stats"]["payload_files"], 3)
        self.assertEqual(index["stats"]["review_files"], 2)
        self.assertEqual(index["stats"]["review_events"], 3)
        self.assertIn("review", index["tag_groups_by_level"])
        self.assertIn("primary", index["tag_groups_by_level"])
        self.assertIn("supporting", index["tag_groups_by_level"])
        self.assertEqual(
            [item["file"] for item in index["files"]],
            ["a_cut_in.json", "c_low_ttc.json"],
        )
        self.assertEqual(index["files"][0]["review_tag_counts"], {"cut_in_risk": 1})
        self.assertEqual(index["files"][0]["review_tag_summaries"]["cut_in_risk"]["count"], 1)
        self.assertEqual(index["files"][0]["first_review_frame_index"], 8)
        self.assertEqual(index["files"][1]["review_tags"], ["persistent_low_ttc_pair", "sdc_repeated_lane_change"])
        self.assertEqual(
            [group["tag_name"] for group in index["tag_groups"]],
            ["cut_in_risk", "persistent_low_ttc_pair", "sdc_repeated_lane_change"],
        )
        self.assertEqual(
            [group["tag_name"] for group in index["tag_groups_by_level"]["primary"]],
            ["cut_in_risk", "persistent_low_ttc_pair", "sdc_repeated_lane_change"],
        )
        self.assertEqual(index["tag_groups"][1]["files"][0]["scenario_id"], "low-ttc")

    def test_index_builds_tag_groups_for_review_levels(self):
        from tools.export_viewer import build_review_payload_index

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            payload = make_payload(
                "mixed",
                [
                    event("sdc_hard_braking", 8, "review"),
                    event("red_light_stop_line_approach", 7, "supporting"),
                    event("vehicle_stopped", 6, "debug"),
                ],
                review_indices=[0],
            )
            payload["event_groups"] = {"primary": [0], "supporting": [1], "debug": [2]}
            (root / "mixed.json").write_text(json.dumps(payload), encoding="utf-8")

            index = build_review_payload_index(root)

        self.assertEqual(index["tag_groups_by_level"]["review"][0]["tag_name"], "sdc_hard_braking")
        self.assertEqual(index["tag_groups_by_level"]["primary"][0]["tag_name"], "sdc_hard_braking")
        self.assertEqual(index["tag_groups_by_level"]["supporting"][0]["tag_name"], "red_light_stop_line_approach")
        self.assertEqual(index["tag_groups_by_level"]["debug"][0]["tag_name"], "vehicle_stopped")
        self.assertEqual(
            [group["tag_name"] for group in index["tag_groups_by_level"]["all"]],
            ["red_light_stop_line_approach", "sdc_hard_braking", "vehicle_stopped"],
        )

    def test_index_can_use_review_events_when_indices_are_absent(self):
        from tools.export_viewer import build_review_payload_index

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            payload = make_payload("legacy", [event("cut_in_risk", 4)])
            payload["review_event_indices"] = []
            payload["review_events"] = [payload["events"][0]]
            (root / "legacy_review.json").write_text(json.dumps(payload), encoding="utf-8")

            index = build_review_payload_index(root)

        self.assertEqual(index["stats"]["review_files"], 1)
        self.assertEqual(index["files"][0]["review_event_count"], 1)
        self.assertEqual(index["files"][0]["first_review_timestamp_seconds"], 0.4)

    def test_render_review_index_html_uses_file_selector_and_iframe(self):
        from tools.export_viewer import render_review_index_html

        index = {
            "payload_dir": "review_payload_bulk",
            "files": [
                {
                    "file": "review_payload_00035.json",
                    "path": "review_payload_00035.json",
                    "viewer_path": "review_viewers/review_payload_00035.html",
                    "scenario_id": "scenario-35",
                    "review_event_count": 1,
                    "review_tag_counts": {"cut_in_risk": 1},
                    "review_tag_summaries": {
                        "cut_in_risk": {
                            "count": 1,
                            "first_frame_index": 8,
                            "first_timestamp_seconds": 0.8,
                        }
                    },
                    "review_tags": ["cut_in_risk"],
                    "first_review_frame_index": 8,
                    "first_review_timestamp_seconds": 0.8,
                    "total_events": 7,
                }
            ],
            "stats": {"payload_files": 100, "review_files": 1, "review_events": 1},
            "diagnostics": [],
        }

        html = render_review_index_html(index)

        self.assertIn('id="reviewFileIndex"', html)
        self.assertIn('id="reviewTagList"', html)
        self.assertIn('id="reviewLevelFilter"', html)
        self.assertNotIn('id="reviewTagFilter"', html)
        self.assertIn('id="viewerFrame"', html)
        self.assertIn("review_payload_00035.json", html)
        self.assertIn("review_viewers/review_payload_00035.html", html)
        self.assertIn("cut_in_risk", html)
        self.assertIn('"tag_name": "cut_in_risk"', html)
        self.assertIn("${escapeHtml(group.tag_name || 'unknown')} (${group.count || 0})", html)
        self.assertIn(".scene-row.selected", html)
        self.assertIn("renderReviewTagGroups", html)
        self.assertIn("reviewLevelFilter.addEventListener", html)
        self.assertNotIn("reviewTagFilter.addEventListener", html)
        self.assertIn("classList.toggle('selected'", html)

    def test_render_review_index_from_payload_dir_writes_index_and_review_viewers(self):
        from tools.export_viewer import render_review_index_from_payload_dir

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "with_review.json").write_text(
                json.dumps(make_payload("with-review", [event("cut_in_risk", 8)])),
                encoding="utf-8",
            )
            (root / "without_review.json").write_text(
                json.dumps(make_payload("without-review", [event("vehicle_stopped", 1, "debug")])),
                encoding="utf-8",
            )
            output = root / "view.html"

            result = render_review_index_from_payload_dir(root, output)

            self.assertEqual(result, output)
            self.assertTrue(output.exists())
            self.assertTrue((root / "review_viewers" / "with_review.html").exists())
            self.assertFalse((root / "review_viewers" / "without_review.html").exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("with_review.json", html)
            self.assertNotIn("without_review.json", html)

    def test_render_review_index_supports_viewer_dir_outside_output_parent(self):
        from tools.export_viewer import render_review_index_from_payload_dir

        with tempfile.TemporaryDirectory() as payload_tmp, tempfile.TemporaryDirectory() as viewer_tmp:
            payload_root = Path(payload_tmp) / "payloads"
            output_root = Path(payload_tmp) / "out"
            viewer_root = Path(viewer_tmp) / "review_viewers"
            payload_root.mkdir()
            output_root.mkdir()
            (payload_root / "with_review.json").write_text(
                json.dumps(make_payload("with-review", [event("cut_in_risk", 8)])),
                encoding="utf-8",
            )

            output = output_root / "view.html"
            result = render_review_index_from_payload_dir(payload_root, output, viewer_root)

            self.assertEqual(result, output)
            self.assertTrue((viewer_root / "with_review.html").exists())
            html = output.read_text(encoding="utf-8")
            self.assertIn("with_review.html", html)


if __name__ == "__main__":
    unittest.main()
