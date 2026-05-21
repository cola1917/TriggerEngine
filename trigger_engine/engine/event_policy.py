from __future__ import annotations

from dataclasses import replace

from trigger_engine.rules.ast import Rule
from trigger_engine.rules.events import TagEvent


class EventPolicyEngine:
    def apply(
        self,
        events: tuple[TagEvent, ...],
        rules: tuple[Rule, ...],
    ) -> tuple[TagEvent, ...]:
        cooldown_by_tag: dict[str, int] = {}
        for rule in rules:
            cooldown = rule.emit.policy.cooldown_frames
            if cooldown > 0:
                cooldown_by_tag[rule.emit.tag_name] = cooldown

        suppressed_until: dict[tuple, int] = {}
        result: list[TagEvent] = []

        for event in events:
            key = (event.scenario_id, event.tag_name, event.subject_type, event.subject_id)
            cooldown = cooldown_by_tag.get(event.tag_name, 0)

            if cooldown <= 0:
                result.append(event)
                continue

            last = suppressed_until.get(key, -1)
            if event.frame_index <= last:
                continue

            new_metadata = dict(event.metadata)
            new_metadata["policy"] = {
                "cooldown_frames": cooldown,
                "suppressed_until_frame_index": event.frame_index + cooldown,
                "output_frame_index": event.frame_index,
                "output_timestamp_seconds": event.timestamp_seconds,
            }
            kept = replace(event, metadata=new_metadata)
            result.append(kept)

            suppressed_until[key] = event.frame_index + cooldown

        return tuple(result)
