import struct
import tempfile
import unittest
from pathlib import Path

from trigger_engine.data.readers import TFRecordReadError, TFRecordScenarioReader, read_tfrecord_payload


def write_record(file_obj, payload):
    file_obj.write(struct.pack("<Q", len(payload)))
    file_obj.write(b"lcRC")
    file_obj.write(payload)
    file_obj.write(b"dcRC")


class ReaderContractTests(unittest.TestCase):
    def test_read_tfrecord_payload_reads_first_record(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "single.tfrecord"
            with open(path, "wb") as file_obj:
                write_record(file_obj, b"first")

            self.assertEqual(read_tfrecord_payload(path), b"first")

    def test_iter_payloads_reads_all_records(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "multi.tfrecord"
            with open(path, "wb") as file_obj:
                write_record(file_obj, b"first")
                write_record(file_obj, b"second")

            payloads = tuple(TFRecordScenarioReader().iter_payloads(path))

        self.assertEqual(payloads, (b"first", b"second"))

    def test_iter_payloads_rejects_truncated_record(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bad.tfrecord"
            with open(path, "wb") as file_obj:
                file_obj.write(struct.pack("<Q", 10))
                file_obj.write(b"lcRC")
                file_obj.write(b"short")

            with self.assertRaisesRegex(TFRecordReadError, "record payload"):
                tuple(TFRecordScenarioReader().iter_payloads(path))

    def test_iter_scenarios_reports_missing_protobuf_clearly(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "single.tfrecord"
            with open(path, "wb") as file_obj:
                write_record(file_obj, b"payload")

            with self.assertRaisesRegex(RuntimeError, "google.protobuf"):
                tuple(TFRecordScenarioReader().iter_scenarios(path))


if __name__ == "__main__":
    unittest.main()
