from __future__ import annotations

import json
import time
from pathlib import Path

from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
from trigger_engine.data.adapters import WaymoScenarioAdapter
from trigger_engine.data.nuscenes_adapter import NuScenesAdapter
from trigger_engine.data.readers import TFRecordScenarioReader


class NuScenesOfflineSource:
    source_type = "nuscenes"

    def __init__(
        self,
        dataroot: Path,
        *,
        version: str = "v1.0-mini",
        scenes: list[str] | None = None,
    ) -> None:
        self.dataroot = dataroot
        self.version = version
        self.scenes = scenes

    def list_units(self) -> list[str]:
        if self.scenes is not None:
            return list(self.scenes)
        scene_path = self.dataroot / self.version / "scene.json"
        scenes = json.loads(scene_path.read_text(encoding="utf-8"))
        return [scene["name"] for scene in scenes]

    def load_bundle(self, unit_id: str):
        return NuScenesAdapter().load(self.dataroot, version=self.version, scene=unit_id)

    def iter_bundles(self):
        for unit_id in self.list_units():
            yield unit_id, self.load_bundle(unit_id)

    def payload_context(self, scenario_bundle, *, future_steps: int):
        return ScenarioAlignment().align(
            scenario_bundle,
            history_steps=len(scenario_bundle.frames) - 1,
            future_steps=future_steps,
        )

    def payload_name(self, unit_id: str, scenario_bundle) -> str:
        return f"nuscenes_{unit_id}.json"


class WaymoOfflineSource:
    source_type = "waymo"

    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths
        self.include_visual_map_features = True

    def configure_for_run(self, config) -> None:
        self.include_visual_map_features = bool(config.write_payloads)

    def list_units(self) -> list[str]:
        units: list[str] = []
        reader = TFRecordScenarioReader()
        for path in self.paths:
            count = 0
            for _ in reader.iter_payloads(path):
                units.append(f"{path}#{count}")
                count += 1
        return units

    def load_bundle(self, unit_id: str):
        path_text, index_text = unit_id.rsplit("#", 1)
        scenario_index = int(index_text)
        reader = TFRecordScenarioReader()
        for index, scenario in enumerate(reader.iter_scenarios(path_text)):
            if index == scenario_index:
                return WaymoScenarioAdapter(
                    include_visual_map_features=self.include_visual_map_features
                ).from_proto(scenario, source=path_text)
        raise ValueError(f"Waymo scenario unit not found: {unit_id}")

    def iter_bundles(self):
        reader = TFRecordScenarioReader()
        adapter = WaymoScenarioAdapter(
            include_visual_map_features=self.include_visual_map_features
        )
        for path in self.paths:
            path_text = str(path)
            scenarios = iter(reader.iter_scenarios(path))
            index = 0
            while True:
                t0 = time.perf_counter()
                try:
                    scenario = next(scenarios)
                except StopIteration:
                    break
                decode_seconds = time.perf_counter() - t0
                t0 = time.perf_counter()
                bundle = adapter.from_proto(scenario, source=path_text)
                adapter_seconds = time.perf_counter() - t0
                timings = {
                    "source_decode_seconds": decode_seconds,
                    "source_adapter_seconds": adapter_seconds,
                    "source_load_seconds": decode_seconds + adapter_seconds,
                }
                yield f"{path_text}#{index}", bundle, timings
                index += 1

    def payload_context(self, scenario_bundle, *, future_steps: int):
        return ScenarioAlignment().align(scenario_bundle, future_steps=future_steps)

    def payload_name(self, unit_id: str, scenario_bundle) -> str:
        path_text, index_text = unit_id.rsplit("#", 1)
        path = Path(path_text)
        return f"waymo_{path.name}_s{int(index_text):04d}.json"


def make_offline_source(
    source_type: str,
    *,
    dataroot: Path | None = None,
    paths: list[Path] | None = None,
    scenes: list[str] | None = None,
    version: str = "v1.0-mini",
):
    if source_type == "nuscenes":
        if dataroot is None:
            raise ValueError("nuscenes source requires dataroot")
        return NuScenesOfflineSource(dataroot, version=version, scenes=scenes)
    if source_type == "waymo":
        if not paths:
            raise ValueError("waymo source requires paths")
        return WaymoOfflineSource(paths)
    raise ValueError(f"Unsupported offline source type: {source_type}")
