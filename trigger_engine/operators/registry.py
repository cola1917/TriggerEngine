from __future__ import annotations

from .base import Operator


class OperatorRegistryError(Exception):
    pass


class OperatorRegistry:
    def __init__(self) -> None:
        self._operators: dict[str, Operator] = {}

    def register(self, operator: Operator) -> None:
        if operator.name in self._operators:
            raise OperatorRegistryError(
                f"Operator '{operator.name}' is already registered"
            )
        self._operators[operator.name] = operator

    def get(self, name: str) -> Operator:
        try:
            return self._operators[name]
        except KeyError:
            raise OperatorRegistryError(f"Operator '{name}' not found")

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._operators.keys()))
