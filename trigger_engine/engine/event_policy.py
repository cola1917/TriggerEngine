from __future__ import annotations

from dataclasses import replace

from trigger_engine.rules.ast import Rule
from trigger_engine.rules.events import TagEvent


def _compact_events(events: tuple[TagEvent, ...], rules: tuple[Rule, ...]) -> tuple[TagEvent, ...]:
    compact_rules: dict[tuple[str, str], str] = {}
    for rule in rules:
        compact = rule.emit.policy.compact
        if compact is not None:
            compact_rules[(rule.emit.tag_name, rule.rule_id)] = compact.by

    if not compact_rules:
        return events

    # Separate compactable and non-compactable events
    compactable: list[TagEvent] = []
    non_compactable: list[TagEvent] = []
    for event in events:
        by_key = compact_rules.get((event.tag_name, event.rule_id))
        intent = event.metadata.get("intent", "debug") if isinstance(event.metadata, dict) else "debug"
        if by_key is not None and intent != "review":
            compactable.append(event)
        else:
            non_compactable.append(event)

    if not compactable:
        return events

    # Sort compactable events by group key then frame_index
    def _sort_key(e: TagEvent):
        return (
            e.scenario_id,
            e.source,
            e.tag_name,
            e.rule_id,
            e.subject_type,
            str(e.subject_id),
            e.frame_index,
        )

    compactable.sort(key=_sort_key)

    # Compact consecutive frames within same group
    result: list[TagEvent] = []
    pending: TagEvent | None = None
    pending_indices: list[int] = []
    pending_timestamps: list[float] = []

    def _flush():
        nonlocal pending
        if pending is None:
            return
        if len(pending_indices) <= 1:
            result.append(pending)
        else:
            new_metadata = dict(pending.metadata)
            new_metadata["compaction"] = {
                "mode": "interval",
                "by": compact_rules.get((pending.tag_name, pending.rule_id), "subject"),
                "start_frame_index": pending.frame_index,
                "end_frame_index": pending_indices[-1],
                "start_timestamp_seconds": pending.timestamp_seconds,
                "end_timestamp_seconds": pending_timestamps[-1],
                "frame_count": len(pending_indices),
                "raw_frame_indices": tuple(pending_indices),
                "raw_timestamps_seconds": tuple(pending_timestamps),
            }
            result.append(replace(pending, metadata=new_metadata))
        pending = None

    for event in compactable:
        group_key = (
            event.scenario_id,
            event.source,
            event.tag_name,
            event.rule_id,
            event.subject_type,
            event.subject_id,
        )
        prev_key = (
            pending.scenario_id,
            pending.source,
            pending.tag_name,
            pending.rule_id,
            pending.subject_type,
            pending.subject_id,
        ) if pending is not None else None

        if pending is not None and group_key == prev_key and event.frame_index == pending_indices[-1] + 1:
            pending_indices.append(event.frame_index)
            pending_timestamps.append(event.timestamp_seconds)
        else:
            _flush()
            pending = event
            pending_indices = [event.frame_index]
            pending_timestamps = [event.timestamp_seconds]

    _flush()

    # Merge and sort by subject then frame_index to maintain consistent ordering
    all_result = list(non_compactable)
    all_result.extend(result)
    all_result.sort(key=lambda e: (str(e.subject_id), e.frame_index, e.tag_name))

    return tuple(all_result)


def _episode_events(events: tuple[TagEvent, ...], rules: tuple[Rule, ...]) -> tuple[TagEvent, ...]:
    episode_rules: dict[tuple[str, str], str] = {}
    for rule in rules:
        episode = rule.emit.policy.episode
        if episode is not None:
            episode_rules[(rule.emit.tag_name, rule.rule_id)] = episode.by

    if not episode_rules:
        return events

    # Separate episode-eligible and other events
    episode_eligible: list[TagEvent] = []
    other: list[TagEvent] = []
    for event in events:
        if (event.tag_name, event.rule_id) in episode_rules:
            episode_eligible.append(event)
        else:
            other.append(event)

    if not episode_eligible:
        return events

    # Sort by group key then frame_index
    def _sort_key(e: TagEvent):
        return (
            e.scenario_id,
            e.source,
            e.tag_name,
            e.rule_id,
            e.subject_type,
            str(e.subject_id),
            e.frame_index,
        )

    episode_eligible.sort(key=_sort_key)

    # Merge consecutive events within same group into episodes
    result: list[TagEvent] = []
    pending: TagEvent | None = None
    pending_indices: list[int] = []
    pending_timestamps: list[float] = []
    pending_supporting: dict[int, float] = {}  # frame_index -> timestamp

    def _flush():
        nonlocal pending
        if pending is None:
            return
        if len(pending_indices) <= 1:
            result.append(pending)
        else:
            new_metadata = dict(pending.metadata)
            sorted_support = sorted(pending_supporting.items())
            new_metadata["episode"] = {
                "mode": "interval",
                "by": episode_rules.get((pending.tag_name, pending.rule_id), "subject"),
                "start_frame_index": pending.frame_index,
                "end_frame_index": pending_indices[-1],
                "start_timestamp_seconds": pending.timestamp_seconds,
                "end_timestamp_seconds": pending_timestamps[-1],
                "event_count": len(pending_indices),
                "raw_event_frame_indices": tuple(pending_indices),
                "raw_event_timestamps_seconds": tuple(pending_timestamps),
                "supporting_frame_indices": tuple(idx for idx, _ in sorted_support),
                "supporting_timestamps_seconds": tuple(round(ts, 10) for _, ts in sorted_support),
            }
            result.append(replace(pending, metadata=new_metadata))
        pending = None

    for event in episode_eligible:
        group_key = (
            event.scenario_id,
            event.source,
            event.tag_name,
            event.rule_id,
            event.subject_type,
            event.subject_id,
        )
        prev_key = (
            pending.scenario_id,
            pending.source,
            pending.tag_name,
            pending.rule_id,
            pending.subject_type,
            pending.subject_id,
        ) if pending is not None else None

        if pending is not None and group_key == prev_key and event.frame_index == pending_indices[-1] + 1:
            pending_indices.append(event.frame_index)
            pending_timestamps.append(event.timestamp_seconds)
            # Merge supporting frames
            support_indices = event.metadata.get("supporting_frame_indices", ())
            support_timestamps = event.metadata.get("supporting_timestamps_seconds", ())
            for idx, ts in zip(support_indices, support_timestamps):
                if idx not in pending_supporting:
                    pending_supporting[idx] = ts
        else:
            _flush()
            pending = event
            pending_indices = [event.frame_index]
            pending_timestamps = [event.timestamp_seconds]
            support_indices = event.metadata.get("supporting_frame_indices", ())
            support_timestamps = event.metadata.get("supporting_timestamps_seconds", ())
            pending_supporting = {}
            for idx, ts in zip(support_indices, support_timestamps):
                if idx not in pending_supporting:
                    pending_supporting[idx] = ts

    _flush()

    # Merge and sort by subject then frame_index
    all_result = list(other)
    all_result.extend(result)
    all_result.sort(key=lambda e: (str(e.subject_id), e.frame_index, e.tag_name))

    return tuple(all_result)


def _review_dominance(events: tuple[TagEvent, ...]) -> tuple[TagEvent, ...]:
    """Suppress lower-priority review events when a higher-priority event in
    the same review family has an overlapping episode interval for the same
    subject."""

    def _dominance_key(e: TagEvent):
        return (e.scenario_id, e.source, e.subject_type, str(e.subject_id),
                e.metadata.get("review_family"))

    def _interval(e: TagEvent):
        ep = e.metadata.get("episode")
        if isinstance(ep, dict):
            return ep.get("start_frame_index"), ep.get("end_frame_index")
        return e.frame_index, e.frame_index

    groups: dict[tuple, list[TagEvent]] = {}
    other: list[TagEvent] = []
    for e in events:
        meta = e.metadata if isinstance(e.metadata, dict) else {}
        if meta.get("review_family") is not None and isinstance(meta.get("review_priority"), (int, float)):
            groups.setdefault(_dominance_key(e), []).append(e)
        else:
            other.append(e)

    if not groups:
        return events

    result = list(other)
    for group_events in groups.values():
        best = max(group_events, key=lambda e: e.metadata["review_priority"])
        best_start, best_end = _interval(best)
        for e in group_events:
            if e is best:
                result.append(e)
                continue
            e_start, e_end = _interval(e)
            if e_start <= best_end and e_end >= best_start:
                continue
            result.append(e)

    result.sort(key=lambda e: (str(e.subject_id), e.frame_index, e.tag_name))
    return tuple(result)


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

        compacted = _compact_events(tuple(result), rules)
        episoded = _episode_events(compacted, rules)
        return _review_dominance(episoded)
