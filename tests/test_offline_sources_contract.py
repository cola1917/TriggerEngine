import tempfile
import unittest
from pathlib import Path


class OfflineSourcesContractTests(unittest.TestCase):
    def test_nuscenes_source_lists_scene_names_from_tables(self):
        from trigger_engine.offline.sources import NuScenesOfflineSource

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            version = root / "v1.0-mini"
            version.mkdir()
            (version / "scene.json").write_text(
                '[{"name": "scene-b"}, {"name": "scene-a"}]',
                encoding="utf-8",
            )

            source = NuScenesOfflineSource(root)

            self.assertEqual(source.source_type, "nuscenes")
            self.assertEqual(source.list_units(), ["scene-b", "scene-a"])
            self.assertEqual(source.payload_name("scene-a", None), "nuscenes_scene-a.json")

    def test_waymo_source_uses_paths_as_units_and_payload_names(self):
        from trigger_engine.offline.sources import WaymoOfflineSource

        with tempfile.TemporaryDirectory() as tmp:
            shard = Path(tmp) / "shard-00001"
            shard.write_bytes(b"")
            source = WaymoOfflineSource([shard])

            self.assertEqual(source.source_type, "waymo")
            self.assertEqual(source.list_units(), [])
            self.assertEqual(
                source.payload_name(f"{shard}#7", None),
                "waymo_shard-00001_s0007.json",
            )

    def test_waymo_source_streams_scenarios_without_prelisting(self):
        from trigger_engine.offline.sources import WaymoOfflineSource

        self.assertTrue(hasattr(WaymoOfflineSource([]), "iter_bundles"))

    def test_source_factory_selects_adapter_by_source_type(self):
        from trigger_engine.offline.sources import make_offline_source

        nusc = make_offline_source("nuscenes", dataroot=Path("data") / "nuscenes-mini")
        waymo = make_offline_source("waymo", paths=[Path("data") / "shard-00001"])

        self.assertEqual(nusc.source_type, "nuscenes")
        self.assertEqual(waymo.source_type, "waymo")


if __name__ == "__main__":
    unittest.main()
