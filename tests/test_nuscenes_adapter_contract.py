import unittest
from pathlib import Path


class NuScenesAdapterContractTests(unittest.TestCase):
    def test_adapter_loads_nuscenes_mini_scene_as_trajectory_bundle(self):
        from trigger_engine.data.nuscenes_adapter import NuScenesAdapter

        dataroot = Path("data") / "nuscenes-mini"
        if not dataroot.exists():
            self.skipTest("nuScenes mini data is not available")

        bundle = NuScenesAdapter().load(dataroot, scene="scene-0061")

        self.assertEqual(bundle.metadata.source_type, "nuscenes")
        self.assertEqual(bundle.metadata.dataset_version, "v1.0-mini")
        self.assertEqual(bundle.metadata.scene_name, "scene-0061")
        self.assertEqual(bundle.metadata.scene_token, bundle.scenario_id)
        self.assertGreater(bundle.metadata.sample_count, 0)
        self.assertEqual(bundle.metadata.map_location, "singapore-onenorth")
        self.assertEqual(bundle.metadata.coordinate_frame, "scene_local_global_axes")
        self.assertEqual(len(bundle.metadata.origin_global_translation), 3)
        self.assertEqual(len(bundle.metadata.origin_global_rotation_wxyz), 4)
        self.assertIsInstance(bundle.metadata.origin_global_yaw_rad, float)
        self.assertEqual(bundle.metadata.native_track_id_type, "str")
        self.assertGreater(len(bundle.frames), 1)
        self.assertEqual(bundle.current_time_index, len(bundle.frames) - 1)
        self.assertEqual(bundle.sdc_track_index, 0)
        self.assertEqual(bundle.frames[-1].phase, "current")
        self.assertIn("lidar", bundle.available_capabilities)
        self.assertIn("map", bundle.available_capabilities)
        self.assertNotIn("traffic_lights", bundle.available_capabilities)
        self.assertGreater(len(bundle.map_features), 0)
        self.assertTrue(any(feature.feature_type == "lane" for feature in bundle.map_features.values()))
        self.assertTrue(any(feature.polygon for feature in bundle.map_features.values()))

        current_agents = bundle.frames[-1].agent_states
        self.assertTrue(any(agent.track_id == "ego" for agent in current_agents))
        self.assertTrue(any(isinstance(agent.track_id, str) for agent in current_agents))
        self.assertEqual(bundle.frames[-1].traffic_lights, ())

    def test_alignment_uses_nuscenes_ego_as_sdc_track(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
        from trigger_engine.data.nuscenes_adapter import NuScenesAdapter

        dataroot = Path("data") / "nuscenes-mini"
        if not dataroot.exists():
            self.skipTest("nuScenes mini data is not available")

        bundle = NuScenesAdapter().load(dataroot, scene="scene-0061")
        context = ScenarioAlignment().align(bundle, history_steps=2)

        self.assertEqual(context.sdc_track_id, "ego")
        self.assertEqual(context.data_source_metadata.source_type, "nuscenes")
        self.assertNotIn("traffic_lights", context.current_frame.available_modalities)
        self.assertEqual([item.visibility for item in context.input_frames], ["observed", "observed", "current"])

    def test_nuscenes_native_hz_quality_alignment_and_classic_rules_smoke(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
        from trigger_engine.data.nuscenes_adapter import NuScenesAdapter
        from trigger_engine.data.quality import TrajectoryQualityAnnotator
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import register_classic_scenario_pack

        dataroot = Path("data") / "nuscenes-mini"
        if not dataroot.exists():
            self.skipTest("nuScenes mini data is not available")

        bundle = NuScenesAdapter().load(
            dataroot,
            scene="scene-0061",
            current_time_index=3,
        )
        annotated = TrajectoryQualityAnnotator().annotate(bundle)
        context = ScenarioAlignment().align(annotated, history_steps=3)
        operators = OperatorRegistry()
        rules = RuleRegistry(operator_registry=operators)
        register_classic_scenario_pack(operators, rules)

        result = TriggerEngine(operators, rules).evaluate(context)

        self.assertEqual(result.scenario_id, bundle.scenario_id)
        self.assertGreater(bundle.metadata.frame_sampling.source_hz, 1.0)
        self.assertFalse(
            [diagnostic for diagnostic in result.diagnostics if diagnostic.message == "rule_deprecation"]
        )
        self.assertIsInstance(annotated.quality_issues, tuple)


if __name__ == "__main__":
    unittest.main()
