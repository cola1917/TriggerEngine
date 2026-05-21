import json
import tempfile
import unittest
from pathlib import Path


class TagEventWriterContractTests(unittest.TestCase):
    def test_tag_event_to_dict_is_json_serializable(self):
        from trigger_engine.rules.events import TagEvent
        from trigger_engine.rules.writers import tag_event_to_dict

        event = TagEvent(
            scenario_id="scenario-rules",
            source="file-001",
            frame_index=1,
            timestamp_seconds=0.1,
            tag_name="vehicle_stopped",
            subject_type="agent",
            subject_id=100,
            value=True,
            rule_id="vehicle_stopped",
            metadata={"operator_results": {"predicate.speed_below": True}},
        )

        data = tag_event_to_dict(event)

        self.assertEqual(data["scenario_id"], "scenario-rules")
        self.assertEqual(data["subject_id"], 100)
        self.assertTrue(data["value"])
        json.dumps(data)

    def test_jsonl_writer_writes_one_event_per_line(self):
        from trigger_engine.rules.events import TagEvent
        from trigger_engine.rules.writers import JsonlTagEventWriter

        events = (
            TagEvent("scenario-rules", "file-001", 1, 0.1, "a", "frame", None, True, "rule-a", {}),
            TagEvent("scenario-rules", "file-001", 2, 0.2, "b", "agent", 100, True, "rule-b", {}),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "events.jsonl"
            JsonlTagEventWriter().write_many(events, path)
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["tag_name"], "a")
        self.assertEqual(json.loads(lines[1])["subject_id"], 100)


if __name__ == "__main__":
    unittest.main()
