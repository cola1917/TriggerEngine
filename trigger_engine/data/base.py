from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .frames import ScenarioBundle


class BaseScenarioAdapter(Protocol):
    @property
    def source_type(self) -> str:
        """Stable data source identifier such as 'waymo' or 'nuscenes'."""

    def load(self, source: str | Path, **kwargs) -> ScenarioBundle:
        """Load one scenario-like unit from an external data source."""
