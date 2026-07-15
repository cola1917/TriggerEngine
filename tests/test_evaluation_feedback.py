import copy
import json
import tempfile
import unittest
from pathlib import Path


RESULT_SCHEMA = (
    Path(__file__).parents[2]
    / "SceneExchangeContracts"
    / "src"
    / "scene_exchange_contracts"
    / "schemas"
    / "shared_exchange_protocol"
    / "evaluation_run_result.schema.json"
)


def _result():
    return copy.deepcopy(json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))["examples"][0])


class EvaluationFeedbackTests(unittest.TestCase):
    def test_pass_result_preserves_identity_and_kpis(self):
        from trigger_engine.contracts.evaluation_feedback import build_scenario_feedback

        result = _result()
        feedback = build_scenario_feedback(result)

        self.assertEqual(feedback["schema_version"], "scenario_feedback.v1")
        self.assertEqual(feedback["identity"]["scene_token"], result["payload"]["scene_id"])
        self.assertEqual(feedback["identity"]["algorithm"], result["payload"]["algorithm"])
        self.assertEqual(feedback["identity"]["odd"], result["payload"]["odd"])
        self.assertEqual(feedback["classification"]["state"], "validated")
        self.assertEqual(feedback["classification"]["disposition"], "pass")
        self.assertEqual(feedback["evaluation"]["summary"], result["payload"]["summary"])

    def test_failed_and_unknown_results_are_distinguished(self):
        from trigger_engine.contracts.evaluation_feedback import build_scenario_feedback

        failed = _result()
        failed["payload"].update(status="failed", runtime_status="failed", outcome="unknown")
        failed["payload"]["error"] = {
            "code": "RUNTIME_FAILED",
            "message": "runtime failed",
            "retryable": True,
        }
        self.assertEqual(build_scenario_feedback(failed)["classification"]["priority"], "high")

        unknown = _result()
        unknown["payload"].update(outcome="unknown", runtime_status="not_run")
        unknown["payload"]["summary"] = {name: None for name in unknown["payload"]["summary"]}
        feedback = build_scenario_feedback(unknown)
        self.assertEqual(feedback["classification"]["state"], "incomplete")
        self.assertTrue(all(value is None for value in feedback["evaluation"]["summary"].values()))

        inconsistent = _result()
        inconsistent["payload"].update(outcome="pass", runtime_status="not_run")
        self.assertEqual(
            build_scenario_feedback(inconsistent)["classification"]["state"],
            "incomplete",
        )

    def test_store_is_idempotent_and_rejects_conflicting_run(self):
        from trigger_engine.contracts.evaluation_feedback import (
            EvaluationFeedbackConflictError,
            build_scenario_feedback,
            store_scenario_feedback,
        )

        feedback = build_scenario_feedback(_result())
        with tempfile.TemporaryDirectory() as directory:
            path, created = store_scenario_feedback(Path(directory), feedback)
            self.assertTrue(created)
            self.assertTrue(path.is_file())
            same_path, created = store_scenario_feedback(Path(directory), feedback)
            self.assertEqual(same_path, path)
            self.assertFalse(created)

            conflict = copy.deepcopy(feedback)
            conflict["evaluation"]["summary"]["collision_count"] = 1
            with self.assertRaises(EvaluationFeedbackConflictError):
                store_scenario_feedback(Path(directory), conflict)

    def test_rejects_noncanonical_scene_identity(self):
        from trigger_engine.contracts.evaluation_feedback import (
            EvaluationFeedbackError,
            build_scenario_feedback,
        )

        result = _result()
        result["payload"]["scene_id"] = "scene-0061"
        with self.assertRaisesRegex(EvaluationFeedbackError, "scene token"):
            build_scenario_feedback(result)


if __name__ == "__main__":
    unittest.main()
