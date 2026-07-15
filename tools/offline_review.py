from __future__ import annotations

from dataclasses import replace
from typing import Iterable, TypeVar

from trigger_engine.rules.events import TagEvent


T = TypeVar("T")
SDC_HARD_BRAKE_EPISODE_MAX_GAP_FRAMES = 20


def chunk_items(items: list[T], batch_size: int) -> list[list[T]]:
    if batch_size <= 0:
        raise ValueError(f"batch_size must be > 0, got {batch_size}")
    return [items[index:index + batch_size] for index in range(0, len(items), batch_size)]


def exact_event_key(event: TagEvent) -> tuple[object, ...]:
    return (
        event.rule_id,
        event.frame_index,
        event.tag_name,
        event.subject_type,
        event.subject_id,
    )


def dedupe_events(events: Iterable[TagEvent]) -> list[TagEvent]:
    deduped: list[TagEvent] = []
    seen = set()
    for event in events:
        key = exact_event_key(event)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped


def compact_review_events(events: Iterable[TagEvent]) -> list[TagEvent]:
    deduped = dedupe_events(events)
    output: list[TagEvent] = []
    hard_brake_groups: dict[tuple[object, ...], list[TagEvent]] = {}

    for event in deduped:
        if event.tag_name == "sdc_hard_braking" and event.subject_type == "sdc_pair":
            hard_brake_groups.setdefault(_sdc_event_group_key(event), []).append(event)
        else:
            output.append(event)

    grouped_keys = set(hard_brake_groups)
    compacted_hard_brakes: list[TagEvent] = []
    for group in hard_brake_groups.values():
        compacted_hard_brakes.append(_compact_hard_brake_group(group))

    result = []
    emitted_hard_brakes = iter(sorted(compacted_hard_brakes, key=_event_order_key))
    next_hard_brake = next(emitted_hard_brakes, None)
    for event in deduped:
        if event.tag_name == "sdc_hard_braking" and event.subject_type == "sdc_pair":
            key = _sdc_event_group_key(event)
            if key not in grouped_keys:
                continue
            while next_hard_brake is not None and _event_order_key(next_hard_brake) <= _event_order_key(event):
                result.append(next_hard_brake)
                next_hard_brake = next(emitted_hard_brakes, None)
            grouped_keys.remove(key)
            continue
        result.append(event)
    while next_hard_brake is not None:
        result.append(next_hard_brake)
        next_hard_brake = next(emitted_hard_brakes, None)
    return sorted(_compact_hard_brake_episodes(result), key=_event_order_key)


def _event_order_key(event: TagEvent) -> tuple[object, ...]:
    return (event.frame_index, event.timestamp_seconds, event.tag_name, str(event.subject_id))


def _sdc_event_group_key(event: TagEvent) -> tuple[object, ...]:
    ego_id = event.metadata.get("ego_id")
    if ego_id is None and isinstance(event.subject_id, str):
        ego_id = event.subject_id.split(":", 1)[0]
    return (
        event.scenario_id,
        event.source,
        event.tag_name,
        event.frame_index,
        ego_id,
    )


def _compact_hard_brake_group(events: list[TagEvent]) -> TagEvent:
    if len(events) == 1:
        return events[0]
    keeper = min(events, key=_hard_brake_priority_key)
    suppressed = [event for event in events if event is not keeper]
    metadata = dict(keeper.metadata)
    metadata["compaction"] = {
        "policy": "sdc_hard_braking_by_ego_frame",
        "suppressed_event_count": len(suppressed),
        "suppressed_targets": [_target_id(event) for event in suppressed],
        "suppressed_subject_ids": [event.subject_id for event in suppressed],
    }
    return replace(keeper, metadata=metadata)


def _hard_brake_priority_key(event: TagEvent) -> tuple[float, float, str]:
    metrics = _operator_metrics(event)
    longitudinal = abs(float(metrics.get("longitudinal_m", 1_000_000.0)))
    lateral = abs(float(metrics.get("lateral_m", 1_000_000.0)))
    return (longitudinal, lateral, str(event.subject_id))


def _operator_metrics(event: TagEvent) -> dict[str, object]:
    operator_metadata = event.metadata.get("operator_metadata")
    if not isinstance(operator_metadata, dict):
        return {}
    for value in operator_metadata.values():
        if isinstance(value, dict):
            return value
    return {}


def _target_id(event: TagEvent) -> str:
    target_id = event.metadata.get("target_id")
    if target_id is not None:
        return str(target_id)
    if isinstance(event.subject_id, str) and ":" in event.subject_id:
        return event.subject_id.split(":", 1)[1]
    return str(event.subject_id)


def _compact_hard_brake_episodes(events: list[TagEvent]) -> list[TagEvent]:
    eligible: list[TagEvent] = []
    other: list[TagEvent] = []
    for event in events:
        if event.tag_name == "sdc_hard_braking" and event.subject_type == "sdc_pair":
            eligible.append(event)
        else:
            other.append(event)

    groups: dict[tuple[object, ...], list[TagEvent]] = {}
    for event in eligible:
        groups.setdefault(_sdc_episode_group_key(event), []).append(event)

    compacted: list[TagEvent] = list(other)
    for group in groups.values():
        compacted.extend(_split_and_compact_hard_brake_episode(group))
    return compacted


def _sdc_episode_group_key(event: TagEvent) -> tuple[object, ...]:
    ego_id = event.metadata.get("ego_id")
    if ego_id is None and isinstance(event.subject_id, str):
        ego_id = event.subject_id.split(":", 1)[0]
    return (
        event.scenario_id,
        event.source,
        event.tag_name,
        event.rule_id,
        event.subject_type,
        ego_id,
    )


def _split_and_compact_hard_brake_episode(events: list[TagEvent]) -> list[TagEvent]:
    ordered = sorted(events, key=_event_order_key)
    episodes: list[list[TagEvent]] = []
    current: list[TagEvent] = []
    for event in ordered:
        if current and event.frame_index - current[-1].frame_index > SDC_HARD_BRAKE_EPISODE_MAX_GAP_FRAMES:
            episodes.append(current)
            current = []
        current.append(event)
    if current:
        episodes.append(current)
    return [_compact_hard_brake_episode(episode) for episode in episodes]


def _compact_hard_brake_episode(events: list[TagEvent]) -> TagEvent:
    if len(events) == 1:
        return events[0]
    keeper = events[0]
    metadata = dict(keeper.metadata)
    metadata["episode"] = {
        "policy": "sdc_hard_braking_by_ego_gap",
        "mode": "interval",
        "by": "ego",
        "max_gap_frames": SDC_HARD_BRAKE_EPISODE_MAX_GAP_FRAMES,
        "start_frame_index": events[0].frame_index,
        "end_frame_index": events[-1].frame_index,
        "start_timestamp_seconds": events[0].timestamp_seconds,
        "end_timestamp_seconds": events[-1].timestamp_seconds,
        "event_count": len(events),
        "raw_event_frame_indices": tuple(event.frame_index for event in events),
        "raw_event_timestamps_seconds": tuple(event.timestamp_seconds for event in events),
        "raw_subject_ids": tuple(event.subject_id for event in events),
    }
    return replace(keeper, metadata=metadata)
