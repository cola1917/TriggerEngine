import unittest


class ReviewBatchRunnerContractTests(unittest.TestCase):
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
                    "seconds": 2.0,
                    "timings": {"engine_seconds": 1.0},
                    "review_scenario_refs": [
                        {
                            "source": "data/shard-00002",
                            "scenario_index": 7,
                            "scenario_id": "b",
                            "review_tags": ["cut_in_confirmed"],
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
