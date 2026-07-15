from __future__ import annotations


class DataAdapterError(Exception):
    pass


def validate_scenario(scenario) -> None:
    _validate_timeline(scenario)
    _validate_current_time_index(scenario)
    _validate_track_lengths(scenario)
    _validate_dynamic_map_states(scenario)
    _validate_sdc_track_index(scenario)
    _validate_tracks_to_predict(scenario)


def _validate_timeline(scenario) -> None:
    if not scenario.timestamps_seconds:
        raise DataAdapterError("timestamps_seconds must not be empty")


def _validate_current_time_index(scenario) -> None:
    n = len(scenario.timestamps_seconds)
    idx = scenario.current_time_index
    if idx < 0 or idx >= n:
        raise DataAdapterError(
            f"current_time_index={idx} out of range [0, {n})"
        )


def _validate_track_lengths(scenario) -> None:
    expected = len(scenario.timestamps_seconds)
    for i, track in enumerate(scenario.tracks):
        actual = len(track.states)
        if actual != expected:
            raise DataAdapterError(
                f"tracks[{i}].states length {actual} != timestamps length {expected}"
            )


def _validate_dynamic_map_states(scenario) -> None:
    expected = len(scenario.timestamps_seconds)
    actual = len(scenario.dynamic_map_states)
    if actual != expected:
        raise DataAdapterError(
            f"dynamic_map_states length {actual} != timestamps length {expected}"
        )


def _validate_sdc_track_index(scenario) -> None:
    n = len(scenario.tracks)
    idx = scenario.sdc_track_index
    if idx < 0 or idx >= n:
        raise DataAdapterError(
            f"sdc_track_index={idx} out of range [0, {n})"
        )


def _validate_tracks_to_predict(scenario) -> None:
    n = len(scenario.tracks)
    for i, ttp in enumerate(scenario.tracks_to_predict):
        idx = ttp.track_index
        if idx < 0 or idx >= n:
            raise DataAdapterError(
                f"tracks_to_predict[{i}].track_index={idx} out of range [0, {n})"
            )
