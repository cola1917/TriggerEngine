import unittest
from dataclasses import is_dataclass


class FakeOperator:
    name = "predicate.always_true"
    result_kind = "predicate"
    subject_type = "frame"

    def evaluate(self, context, frame, subject, args):
        from trigger_engine.operators.base import OperatorResult

        return OperatorResult(
            operator_name=self.name,
            subject_type="frame",
            subject_id=None,
            frame_index=frame.frame.step_index,
            timestamp_seconds=frame.frame.timestamp_seconds,
            value=True,
            metadata={"args": dict(args)},
        )


class OperatorRegistryContractTests(unittest.TestCase):
    def test_operator_result_is_dataclass(self):
        from trigger_engine.operators.base import OperatorResult

        self.assertTrue(is_dataclass(OperatorResult))

        result = OperatorResult(
            operator_name="predicate.speed_below",
            subject_type="agent",
            subject_id=100,
            frame_index=2,
            timestamp_seconds=0.2,
            value=True,
            metadata={"threshold_mps": 0.5},
        )

        self.assertEqual(result.operator_name, "predicate.speed_below")
        self.assertEqual(result.subject_id, 100)
        self.assertTrue(result.value)

    def test_registry_registers_and_returns_operator_by_name(self):
        from trigger_engine.operators.registry import OperatorRegistry

        registry = OperatorRegistry()
        operator = FakeOperator()

        registry.register(operator)

        self.assertIs(registry.get("predicate.always_true"), operator)
        self.assertEqual(registry.names(), ("predicate.always_true",))

    def test_registry_rejects_duplicate_operator_names(self):
        from trigger_engine.operators.registry import OperatorRegistry, OperatorRegistryError

        registry = OperatorRegistry()
        registry.register(FakeOperator())

        with self.assertRaisesRegex(OperatorRegistryError, "predicate.always_true"):
            registry.register(FakeOperator())

    def test_registry_reports_missing_operator(self):
        from trigger_engine.operators.registry import OperatorRegistry, OperatorRegistryError

        with self.assertRaisesRegex(OperatorRegistryError, "predicate.missing"):
            OperatorRegistry().get("predicate.missing")


if __name__ == "__main__":
    unittest.main()
