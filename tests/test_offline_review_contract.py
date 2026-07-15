import unittest

from trigger_engine.rules.events import TagEvent


class OfflineReviewContractTests(unittest.TestCase):
    def test_chunk_items_uses_fixed_size_and_keeps_short_final_batch(self):
        from tools.offline_review import chunk_items

        self.assertEqual(
            chunk_items(["s1", "s2", "s3", "s4", "s5", "s6"], 5),
            [["s1", "s2", "s3", "s4", "s5"], ["s6"]],
        )

    def test_compact_review_events_collapses_sdc_hard_braking_targets(self):
        from tools.offline_review import compact_review_events

        events = [
            TagEvent(
                "scene",
                "unit",
                7,
                0.7,
                "sdc_hard_braking",
                "sdc_pair",
                "ego:near",
                True,
                "sdc_hard_braking",
                {
                    "intent": "review",
                    "risk_level": "high",
                    "ego_id": "ego",
                    "target_id": "near",
                    "operator_metadata": {
                        "predicate.sdc_hard_braking": {
                            "longitudinal_m": 5.0,
                            "lateral_m": 0.4,
                        }
                    },
                },
            ),
            TagEvent(
                "scene",
                "unit",
                7,
                0.7,
                "sdc_hard_braking",
                "sdc_pair",
                "ego:far",
                True,
                "sdc_hard_braking",
                {
                    "intent": "review",
                    "risk_level": "high",
                    "ego_id": "ego",
                    "target_id": "far",
                    "operator_metadata": {
                        "predicate.sdc_hard_braking": {
                            "longitudinal_m": 25.0,
                            "lateral_m": 0.2,
                        }
                    },
                },
            ),
            TagEvent(
                "scene",
                "unit",
                7,
                0.7,
                "vru_close_interaction",
                "sdc_pair",
                "ego:ped",
                True,
                "vru_close_interaction",
                {"intent": "review", "risk_level": "high", "target_id": "ped"},
            ),
        ]

        compacted = compact_review_events(events)

        self.assertEqual([event.tag_name for event in compacted], ["sdc_hard_braking", "vru_close_interaction"])
        hard_brake = compacted[0]
        self.assertEqual(hard_brake.subject_id, "ego:near")
        self.assertEqual(hard_brake.metadata["compaction"]["suppressed_event_count"], 1)
        self.assertEqual(hard_brake.metadata["compaction"]["suppressed_targets"], ["far"])

    def test_compact_review_events_keeps_separate_hard_brake_episodes(self):
        from tools.offline_review import compact_review_events

        events = [
            TagEvent("scene", "unit", 7, 0.7, "sdc_hard_braking", "sdc_pair", "ego:a", True, "r", {"intent": "review"}),
            TagEvent("scene", "unit", 40, 4.0, "sdc_hard_braking", "sdc_pair", "ego:b", True, "r", {"intent": "review"}),
        ]

        self.assertEqual(len(compact_review_events(events)), 2)

    def test_compact_review_events_collapses_hard_braking_episode_by_ego(self):
        from tools.offline_review import compact_review_events

        events = [
            TagEvent("scene", "unit", 4, 0.4, "sdc_hard_braking", "sdc_pair", "ego:a", True, "r", {"intent": "review"}),
            TagEvent("scene", "unit", 8, 0.8, "sdc_hard_braking", "sdc_pair", "ego:b", True, "r", {"intent": "review"}),
            TagEvent("scene", "unit", 9, 0.9, "sdc_hard_braking", "sdc_pair", "ego:c", True, "r", {"intent": "review"}),
        ]

        compacted = compact_review_events(events)

        self.assertEqual(len(compacted), 1)
        self.assertEqual(compacted[0].frame_index, 4)
        self.assertEqual(compacted[0].metadata["episode"]["policy"], "sdc_hard_braking_by_ego_gap")
        self.assertEqual(compacted[0].metadata["episode"]["raw_event_frame_indices"], (4, 8, 9))


if __name__ == "__main__":
    unittest.main()
