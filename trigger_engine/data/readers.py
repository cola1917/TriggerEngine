from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator


class TFRecordReadError(Exception):
    pass


def _read_exact(file_obj, size: int, label: str) -> bytes:
    data = file_obj.read(size)
    if len(data) != size:
        raise TFRecordReadError(f"Expected {size} bytes for {label}, got {len(data)}.")
    return data


def read_tfrecord_payload(path: str | Path) -> bytes:
    with open(path, "rb") as f:
        length_bytes = _read_exact(f, 8, "record length")
        length = struct.unpack("<Q", length_bytes)[0]
        _read_exact(f, 4, "length crc")
        data = _read_exact(f, length, "record payload")
        _read_exact(f, 4, "data crc")
        return data


class TFRecordScenarioReader:
    def iter_payloads(self, path: str | Path) -> Iterator[bytes]:
        with open(path, "rb") as f:
            while True:
                header = f.read(8)
                if len(header) == 0:
                    break
                if len(header) < 8:
                    raise TFRecordReadError("Truncated record length header")
                length = struct.unpack("<Q", header)[0]
                _read_exact(f, 4, "length crc")
                data = _read_exact(f, length, "record payload")
                _read_exact(f, 4, "data crc")
                yield data

    def iter_scenarios(self, path: str | Path):
        try:
            from waymo_open_dataset.protos import scenario_pb2
        except ModuleNotFoundError as exc:
            if exc.name == "google":
                raise RuntimeError(
                    "Missing dependency: google.protobuf. "
                    "Install protobuf before parsing Waymo scenarios."
                ) from exc
            raise

        for payload in self.iter_payloads(path):
            scenario = scenario_pb2.Scenario()
            try:
                scenario.ParseFromString(payload)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to parse google.protobuf Scenario: {exc}"
                ) from exc
            yield scenario
