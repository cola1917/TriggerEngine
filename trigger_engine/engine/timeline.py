from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from trigger_engine.rules.events import TagEvent


@dataclass(frozen=True)
class TagKey:
    tag_name: str
    subject_type: str
    subject_id: str | int | None


class TagTimeline:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str, str | int | None, int], bool] = {}
        self._events: dict[tuple[str, str, str | int | None, int], TagEvent] = {}
        self._timestamps: dict[int, float] = {}
        self._subject_frames: dict[tuple[str, str, str | int | None], set[int]] = {}
        self._tag_subjects: dict[tuple[str, str], set[str | int | None]] = {}

    @classmethod
    def from_events(cls, events: Iterable[TagEvent]) -> TagTimeline:
        timeline = cls()
        for event in events:
            key = (event.tag_name, event.subject_type, event.subject_id, event.frame_index)
            timeline._data[key] = True
            timeline._events[key] = event
            timeline._timestamps[event.frame_index] = event.timestamp_seconds
            sf_key = (event.tag_name, event.subject_type, event.subject_id)
            timeline._subject_frames.setdefault(sf_key, set()).add(event.frame_index)
            ts_key = (event.tag_name, event.subject_type)
            timeline._tag_subjects.setdefault(ts_key, set()).add(event.subject_id)
        return timeline

    def has_at(self, key: TagKey, frame_index: int) -> bool:
        return self._data.get(
            (key.tag_name, key.subject_type, key.subject_id, frame_index), False
        )

    def event_at(self, key: TagKey, frame_index: int) -> TagEvent | None:
        return self._events.get(
            (key.tag_name, key.subject_type, key.subject_id, frame_index)
        )

    def timestamp_at(self, frame_index: int) -> float:
        return self._timestamps[frame_index]

    def subject_ids_for(self, tag_name: str, subject_type: str) -> tuple[str | int | None, ...]:
        return tuple(sorted(
            self._tag_subjects.get((tag_name, subject_type), set()),
            key=str,
        ))

    def frames_for(self, key: TagKey) -> tuple[int, ...]:
        return tuple(sorted(
            self._subject_frames.get((key.tag_name, key.subject_type, key.subject_id), set())
        ))

    def sustained(
        self,
        key: TagKey,
        end_frame_index: int,
        frames: int,
    ) -> tuple[bool, tuple[int, ...]]:
        supporting: list[int] = []
        for i in range(end_frame_index - frames + 1, end_frame_index + 1):
            if not self.has_at(key, i):
                return False, ()
            supporting.append(i)
        return True, tuple(supporting)

    def sustained_seconds(
        self,
        key: TagKey,
        end_frame_index: int,
        seconds: float,
    ) -> tuple[bool, tuple[int, ...]]:
        end_ts = self._timestamps.get(end_frame_index)
        if end_ts is None:
            return False, ()

        supporting: list[int] = []
        for i in range(end_frame_index, -1, -1):
            ts = self._timestamps.get(i)
            if ts is None:
                break
            if end_ts - ts > seconds:
                break
            if self.has_at(key, i):
                supporting.append(i)
            else:
                break

        if not supporting:
            return False, ()

        supporting.reverse()

        first_ts = self._timestamps[supporting[0]]
        if end_ts - first_ts < seconds:
            return False, ()

        return True, tuple(supporting)

    def sequence(
        self,
        keys: tuple[TagKey, ...],
        end_frame_index: int,
        within_frames: int,
    ) -> tuple[bool, tuple[int, ...]]:
        if not keys or within_frames <= 0:
            return False, ()

        start_frame_index = end_frame_index - within_frames + 1
        next_search_start = start_frame_index
        supporting: list[int] = []

        for key in keys:
            matched_frame = None
            for frame_index in range(next_search_start, end_frame_index + 1):
                if self.has_at(key, frame_index):
                    matched_frame = frame_index
                    break
            if matched_frame is None:
                return False, ()
            supporting.append(matched_frame)
            next_search_start = matched_frame

        return True, tuple(supporting)

    def sequence_seconds(
        self,
        keys: tuple[TagKey, ...],
        end_frame_index: int,
        within_seconds: float,
        max_gap_frames: int | None = None,
    ) -> tuple[bool, tuple[int, ...]]:
        if not keys:
            return False, ()

        end_ts = self._timestamps.get(end_frame_index)
        if end_ts is None:
            return False, ()

        start_ts = end_ts - within_seconds
        next_search_start = 0
        supporting: list[int] = []

        for key in keys:
            matched_frame = None
            for frame_index in range(next_search_start, end_frame_index + 1):
                ts = self._timestamps.get(frame_index)
                if ts is None or ts < start_ts or ts > end_ts:
                    continue
                if self.has_at(key, frame_index):
                    matched_frame = frame_index
                    break
            if matched_frame is None:
                return False, ()
            if (
                max_gap_frames is not None
                and supporting
                and matched_frame - supporting[-1] - 1 > max_gap_frames
            ):
                return False, ()
            supporting.append(matched_frame)
            next_search_start = matched_frame

        first_ts = self._timestamps.get(supporting[0])
        last_ts = self._timestamps.get(supporting[-1])
        if first_ts is None or last_ts is None:
            return False, ()
        if end_ts - first_ts > within_seconds:
            return False, ()

        return True, tuple(supporting)
