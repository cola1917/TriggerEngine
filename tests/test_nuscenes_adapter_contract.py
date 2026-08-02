import json
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

        lane_features = [
            feature for feature in bundle.map_features.values()
            if feature.feature_type == "lane"
        ]
        self.assertTrue(lane_features)
        self.assertTrue(all(feature.polyline for feature in lane_features))
        self.assertIn("lane_geometry", bundle.available_capabilities)
        self.assertTrue(
            all("entry_lanes" in feature.properties for feature in lane_features)
        )
        self.assertTrue(
            any(feature.properties.get("exit_lanes") for feature in lane_features)
        )
        self.assertTrue(
            any("lane centerlines" in note for note in bundle.metadata.notes)
        )

    def test_all_nuscenes_mini_maps_normalize_lane_centerlines(self):
        from trigger_engine.data.nuscenes_adapter import NuScenesAdapter

        dataroot = Path("data") / "nuscenes-mini"
        if not dataroot.exists():
            self.skipTest("nuScenes mini data is not available")

        scene_records = json.loads(
            (dataroot / "v1.0-mini" / "scene.json").read_text(encoding="utf-8")
        )
        adapter = NuScenesAdapter()
        for scene_record in scene_records:
            bundle = adapter.load(dataroot, scene=scene_record["name"])
            lanes = [
                feature for feature in bundle.map_features.values()
                if feature.feature_type == "lane"
            ]
            self.assertTrue(lanes, scene_record["name"])
            self.assertTrue(
                all(feature.polyline for feature in lanes),
                scene_record["name"],
            )
            for lane in lanes:
                for successor_id in lane.properties["exit_lanes"]:
                    self.assertIn(
                        lane.feature_id,
                        bundle.map_features[successor_id].properties["entry_lanes"],
                    )

    def test_real_nuscenes_lane_matching_uses_map_lane_geometry(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
        from trigger_engine.data.nuscenes_adapter import NuScenesAdapter
        from trigger_engine.operators.builtins import (
            AgentPairSubject,
            register_builtin_operators,
        )
        from trigger_engine.operators.lane_matching import match_agent_to_lane_cached
        from trigger_engine.operators.registry import OperatorRegistry

        dataroot = Path("data") / "nuscenes-mini"
        if not dataroot.exists():
            self.skipTest("nuScenes mini data is not available")

        bundle = NuScenesAdapter().load(dataroot, scene="scene-0061")
        context = ScenarioAlignment().align(bundle)
        valid_agents = [
            agent for agent in context.current_frame.frame.agent_states if agent.valid
        ]
        matches = [
            match_agent_to_lane_cached(
                context,
                agent,
                bundle.map_features,
                max_lateral_m=1.8,
                max_heading_delta_rad=0.7,
            )
            for agent in valid_agents
        ]

        self.assertIn("lane_geometry", context.current_frame.available_modalities)
        self.assertGreater(sum(match is not None for match in matches), 0)

        operators = OperatorRegistry()
        register_builtin_operators(operators)
        same_lane_args = {
            "max_lane_lateral_m": 1.8,
            "max_heading_delta_rad": 0.7,
            "fallback_max_lateral_m": 1.2,
            "fallback_max_heading_delta_rad": 0.35,
            "allow_fallback_without_map": True,
        }
        vehicles = [
            agent for agent in valid_agents
            if agent.object_type == "vehicle"
        ]
        lane_mode_found = False
        for ego in vehicles:
            for other in vehicles:
                if ego.track_id == other.track_id:
                    continue
                result = operators.get("predicate.same_lane_or_path").evaluate(
                    context,
                    context.current_frame,
                    AgentPairSubject(ego=ego, other=other),
                    same_lane_args,
                )
                if result.metadata.get("mode") == "lane":
                    lane_mode_found = True
                    break
            if lane_mode_found:
                break
        self.assertTrue(lane_mode_found)

    def test_nuscenes_signal_rules_require_unavailable_dynamic_signal_state(self):
        from trigger_engine.rules.parser import RuleParser
        from trigger_engine.scenarios.classic import CLASSIC_SCENARIO_RULES_YAML

        rules = RuleParser().parse_yaml(CLASSIC_SCENARIO_RULES_YAML)
        by_id = {rule.rule_id: rule for rule in rules.rules}

        self.assertEqual(
            by_id["sdc_vehicle_stopped_at_red"].required_modalities,
            frozenset({"traffic_lights"}),
        )
        for rule_id in (
            "red_light_stop_line_approach",
            "red_light_stop_line_crossed",
            "red_light_running",
        ):
            self.assertEqual(
                by_id[rule_id].required_modalities,
                frozenset({"traffic_lights", "lane_geometry"}),
            )

    def test_nuscenes_classic_signal_rules_are_skipped_without_signal_frames(self):
        from trigger_engine.alignment.scenario_alignment import ScenarioAlignment
        from trigger_engine.data.nuscenes_adapter import NuScenesAdapter
        from trigger_engine.engine.registry import RuleRegistry
        from trigger_engine.engine.trigger_engine import TriggerEngine
        from trigger_engine.operators.builtins import register_builtin_operators
        from trigger_engine.operators.registry import OperatorRegistry
        from trigger_engine.scenarios.classic import register_classic_scenario_pack

        dataroot = Path("data") / "nuscenes-mini"
        if not dataroot.exists():
            self.skipTest("nuScenes mini data is not available")

        bundle = NuScenesAdapter().load(dataroot, scene="scene-0061")
        context = ScenarioAlignment().align(bundle)
        operators = OperatorRegistry()
        rules = RuleRegistry(operator_registry=operators)
        register_builtin_operators(operators)
        register_classic_scenario_pack(operators, rules)
        result = TriggerEngine(operators, rules, profile_rules=True).evaluate(context)

        profiles = {
            diagnostic.metadata["rule_id"]: diagnostic.metadata
            for diagnostic in result.diagnostics
            if diagnostic.message == "rule_profile"
        }
        for rule_id in (
            "sdc_vehicle_stopped_at_red",
            "red_light_stop_line_approach",
            "red_light_stop_line_crossed",
            "red_light_running",
        ):
            self.assertEqual(profiles[rule_id]["frames_evaluated"], 0)
            self.assertGreater(profiles[rule_id]["frames_skipped"], 0)

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
