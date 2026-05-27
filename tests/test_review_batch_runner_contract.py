import unittest


class ReviewBatchRunnerContractTests(unittest.TestCase):
    def test_count_events_reports_risk_and_unique_targets(self):
        from tools.run_review_batch import _count_events

        events = [
            {
                "tag_name": "vru_close_interaction",
                "subject_type": "sdc_pair",
                "subject_id": "1:20",
                "metadata": {"intent": "review", "risk_level": "high"},
            },
            {
                "tag_name": "vru_close_interaction",
                "subject_type": "sdc_pair",
                "subject_id": "1:21",
                "metadata": {"intent": "review", "risk_level": "medium"},
            },
        ]

        stats = _count_events(events)

        self.assertEqual(stats["event_count"], 2)
        self.assertEqual(stats["tag_counts"], {"vru_close_interaction": 2})
        self.assertEqual(stats["risk_counts"], {"high": 1, "medium": 1})
        self.assertEqual(stats["unique_target_count"], 2)

    def test_medium_vru_is_kept_for_payload_but_not_default_review(self):
        from tools.export_viewer import classify_event_group
        from tools.run_review_batch import should_keep_payload_event

        event = {
            "tag_name": "vru_close_interaction",
            "metadata": {"intent": "review", "risk_level": "medium"},
        }

        self.assertEqual(classify_event_group(event), "supporting")
        self.assertTrue(should_keep_payload_event(event))

    def test_merge_shard_summaries_is_deterministic_and_counts_reviews(self):
        from tools.run_review_batch import merge_shard_summaries

        summary = merge_shard_summaries(
            [
                {
                    "path": "data/shard-00002",
                    "file": "shard-00002",
                    "scenarios": 3,
                    "review_scenarios": 1,
                    "review_event_counts": {"cut_in_confirmed": 1},
                    "review_quality": {
                        "payload_scenarios": 2,
                        "multi_event_scenarios": 1,
                        "candidate_event_counts": {"cut_in_confirmed": 1, "vru_close_interaction": 2},
                        "review_risk_counts": {"high": 1},
                        "candidate_risk_counts": {"high": 1, "medium": 2},
                    },
                    "seconds": 2.0,
                    "timings": {"engine_seconds": 1.0},
                    "review_scenario_refs": [
                        {
                            "source": "data/shard-00002",
                            "scenario_index": 7,
                            "scenario_id": "b",
                            "review_tags": ["cut_in_confirmed"],
                            "primary_event_count": 2,
                            "candidate_event_count": 3,
                            "unique_target_count": 2,
                        }
                    ],
                    "payload_outputs": ["payloads/review_payload_00002_s0007.json"],
                },
                {
                    "path": "data/shard-00001",
                    "file": "shard-00001",
                    "scenarios": 2,
                    "review_scenarios": 1,
                    "review_event_counts": {"red_light_running": 1},
                    "review_quality": {
                        "payload_scenarios": 1,
                        "multi_event_scenarios": 0,
                        "candidate_event_counts": {"red_light_running": 1},
                        "review_risk_counts": {"high": 1},
                        "candidate_risk_counts": {"high": 1},
                    },
                    "seconds": 1.0,
                    "timings": {"engine_seconds": 0.5},
                    "review_scenario_refs": [
                        {
                            "source": "data/shard-00001",
                            "scenario_index": 3,
                            "scenario_id": "a",
                            "review_tags": ["red_light_running"],
                        }
                    ],
                    "payload_outputs": ["payloads/review_payload_00001_s0003.json"],
                },
            ],
            elapsed=4.0,
        )

        self.assertEqual(summary["total_scenarios"], 5)
        self.assertEqual(summary["review_scenarios"], 2)
        self.assertEqual(
            summary["review_event_counts"],
            {"cut_in_confirmed": 1, "red_light_running": 1},
        )
        self.assertEqual(summary["review_quality"]["payload_scenarios"], 3)
        self.assertEqual(summary["review_quality"]["multi_event_scenarios"], 1)
        self.assertEqual(
            summary["review_quality"]["candidate_event_counts"],
            {"cut_in_confirmed": 1, "red_light_running": 1, "vru_close_interaction": 2},
        )
        self.assertEqual(
            summary["review_quality"]["candidate_risk_counts"],
            {"high": 2, "medium": 2},
        )
        self.assertEqual(summary["review_quality"]["top_multi_event_scenarios"][0]["scenario_id"], "b")
        self.assertEqual(summary["timings"], {"engine_seconds": 1.5})
        self.assertEqual(
            [ref["scenario_id"] for ref in summary["review_scenario_refs"]],
            ["a", "b"],
        )
        self.assertEqual(
            summary["payload_outputs"],
            [
                "payloads/review_payload_00001_s0003.json",
                "payloads/review_payload_00002_s0007.json",
            ],
        )
        self.assertEqual(list(summary["files"].keys()), ["shard-00001", "shard-00002"])


if __name__ == "__main__":
    unittest.main()
