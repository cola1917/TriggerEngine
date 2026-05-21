import unittest


def event(tag_name, frame_index, subject_id):
    from trigger_engine.rules.events import TagEvent

    return TagEvent(
        scenario_id="scenario-core",
        source="file-001",
        frame_index=frame_index,
        timestamp_seconds=frame_index * 0.1,
        tag_name=tag_name,
        subject_type="agent",
        subject_id=subject_id,
        value=True,
        rule_id=tag_name,
        metadata={},
    )


class TagTimelineContractTests(unittest.TestCase):
    def test_timeline_checks_tag_presence_by_subject_and_frame(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline

        timeline = TagTimeline.from_events((event("vehicle_stopped", 1, 100),))

        self.assertTrue(timeline.has_at(TagKey("vehicle_stopped", "agent", 100), 1))
        self.assertFalse(timeline.has_at(TagKey("vehicle_stopped", "agent", 200), 1))
        self.assertFalse(timeline.has_at(TagKey("vehicle_stopped", "agent", 100), 2))

    def test_timeline_sustained_returns_supporting_frame_indices(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline

        timeline = TagTimeline.from_events(
            (
                event("vehicle_stopped", 0, 100),
                event("vehicle_stopped", 1, 100),
                event("vehicle_stopped", 2, 100),
                event("vehicle_stopped", 2, 200),
            )
        )

        ok, frames = timeline.sustained(TagKey("vehicle_stopped", "agent", 100), 2, 3)

        self.assertTrue(ok)
        self.assertEqual(frames, (0, 1, 2))

    def test_timeline_sustained_does_not_cross_subjects_or_skip_frames(self):
        from trigger_engine.engine.timeline import TagKey, TagTimeline

        timeline = TagTimeline.from_events(
            (
                event("vehicle_stopped", 0, 100),
                event("vehicle_stopped", 2, 100),
                event("vehicle_stopped", 1, 200),
            )
        )

        ok, frames = timeline.sustained(TagKey("vehicle_stopped", "agent", 100), 2, 3)

        self.assertFalse(ok)
        self.assertEqual(frames, ())


if __name__ == "__main__":
    unittest.main()
