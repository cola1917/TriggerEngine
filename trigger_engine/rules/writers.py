from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .events import TagEvent


def tag_event_to_dict(event: TagEvent) -> dict[str, object]:
    return asdict(event)


class JsonlTagEventWriter:
    def write_many(self, events: Iterable[TagEvent], path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for event in events:
                line = json.dumps(tag_event_to_dict(event), ensure_ascii=False)
                f.write(line + "\n")
