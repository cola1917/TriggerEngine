import struct
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

import inspect_frame


def write_tfrecord(path, payload, length_crc=b"lcRC", data_crc=b"dcRC"):
    with open(path, "wb") as file_obj:
        file_obj.write(struct.pack("<Q", len(payload)))
        file_obj.write(length_crc)
        file_obj.write(payload)
        file_obj.write(data_crc)


class Feature(SimpleNamespace):
    def WhichOneof(self, _name):
        return self.feature_type


class LaneState(SimpleNamespace):
    def HasField(self, name):
        return name == "stop_point" and getattr(self, "stop_point", None) is not None


class InspectFrameTests(unittest.TestCase):
    def test_read_tfrecord_returns_first_payload(self):
        payload = b"scenario bytes"
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.tfrecord"
            write_tfrecord(path, payload)

            self.assertEqual(inspect_frame.read_tfrecord(path), payload)

    def test_read_tfrecord_rejects_truncated_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "truncated.tfrecord"
            with open(path, "wb") as file_obj:
                file_obj.write(struct.pack("<Q", 10))
                file_obj.write(b"lcRC")
                file_obj.write(b"short")

            with self.assertRaisesRegex(inspect_frame.TFRecordFormatError, "record payload"):
                inspect_frame.read_tfrecord(path)

    def test_parse_scenario_reports_missing_protobuf_clearly(self):
        with self.assertRaisesRegex(RuntimeError, "google.protobuf"):
            inspect_frame.parse_scenario(b"not a protobuf")

    def test_main_returns_zero_after_successful_inspection(self):
        with mock.patch.object(inspect_frame, "inspect_frame") as inspect_mock:
            self.assertEqual(inspect_frame.main(["sample.tfrecord"]), 0)

        inspect_mock.assert_called_once_with("sample.tfrecord")

    def test_build_report_includes_scenario_tracks_map_and_predictions(self):
        state = SimpleNamespace(
            center_x=1.0,
            center_y=2.0,
            center_z=3.0,
            length=4.0,
            width=5.0,
            height=6.0,
            heading=0.7,
            velocity_x=8.0,
            velocity_y=9.0,
            valid=True,
        )
        track = SimpleNamespace(id=42, object_type=1, states=[state])
        lane = SimpleNamespace(
            type=2,
            speed_limit_mph=35.0,
            polyline=[object(), object()],
            entry_lanes=[1],
            exit_lanes=[2],
            left_boundaries=[],
            right_boundaries=[object()],
            left_neighbors=[],
            right_neighbors=[],
        )
        feature = Feature(id=99, feature_type="lane", lane=lane)
        dynamic_state = SimpleNamespace(
            lane_states=[
                LaneState(
                    lane=123,
                    state=6,
                    stop_point=SimpleNamespace(x=10.0, y=11.0),
                )
            ]
        )
        scenario = SimpleNamespace(
            scenario_id="scenario-test",
            timestamps_seconds=[0.0, 0.1, 0.2],
            current_time_index=0,
            sdc_track_index=0,
            objects_of_interest=[42],
            tracks_to_predict=[SimpleNamespace(track_index=0, difficulty=1)],
            tracks=[track],
            map_features=[feature],
            dynamic_map_states=[dynamic_state],
        )

        report = inspect_frame.build_report(scenario)

        self.assertIn("scenario_id: scenario-test", report)
        self.assertIn("[0] id=42, type=VEHICLE", report)
        self.assertIn("MapFeature[0]: id=99, type=lane", report)
        self.assertIn("lane=123, state=GO", report)
        self.assertIn("difficulty=LEVEL_1", report)


if __name__ == "__main__":
    unittest.main()
