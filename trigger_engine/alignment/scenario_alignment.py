from __future__ import annotations

from dataclasses import replace

from trigger_engine.data.frames import ScenarioBundle

from .context import AlignedFrame, AlignmentContext, Watermark


class AlignmentError(Exception):
    pass


def _available_modalities(bundle: ScenarioBundle, frame) -> frozenset[str]:
    modalities = set()
    if frame.agent_states:
        modalities.add("agents")
    if any(agent.valid for agent in frame.agent_states):
        modalities.add("valid_agents")
    if frame.traffic_lights:
        modalities.add("traffic_lights")
    if bundle.map_features:
        modalities.add("map")
    if bundle.has_lidar_data and frame.step_index <= bundle.current_time_index:
        modalities.add("lidar")
    return frozenset(modalities)


class ScenarioAlignment:
    def align(
        self,
        bundle: ScenarioBundle,
        history_steps: int | None = None,
        future_steps: int | None = None,
    ) -> AlignmentContext:
        if not bundle.frames:
            raise AlignmentError("bundle.frames must not be empty")

        current_time_index = bundle.current_time_index
        if current_time_index < 0 or current_time_index >= len(bundle.frames):
            raise AlignmentError(
                f"current_time_index={current_time_index} out of range [0, {len(bundle.frames)})"
            )

        current_frame = bundle.frames[current_time_index]
        if current_frame.step_index != current_time_index:
            raise AlignmentError(
                f"current frame step_index={current_frame.step_index} "
                f"!= current_time_index={current_time_index}"
            )

        if history_steps is not None and history_steps < 0:
            raise AlignmentError(f"history_steps must be >= 0, got {history_steps}")
        if future_steps is not None and future_steps < 0:
            raise AlignmentError(f"future_steps must be >= 0, got {future_steps}")

        watermark = Watermark(
            scenario_id=bundle.scenario_id,
            step_index=current_time_index,
            timestamp_seconds=current_frame.timestamp_seconds,
        )

        # Build observed frames
        observed_start = 0
        if history_steps is not None:
            observed_start = max(0, current_time_index - history_steps)

        observed_frames = []
        for i in range(observed_start, current_time_index):
            f = bundle.frames[i]
            af = AlignedFrame(
                frame=f,
                visibility="observed",
                available_modalities=_available_modalities(bundle, f),
            )
            observed_frames.append(af)

        # Build current frame
        current_aligned = AlignedFrame(
            frame=current_frame,
            visibility="current",
            available_modalities=_available_modalities(bundle, current_frame),
        )

        # Build future frames
        future_end = len(bundle.frames)
        if future_steps is not None:
            future_end = min(future_end, current_time_index + 1 + future_steps)

        future_frames = []
        for i in range(current_time_index + 1, future_end):
            f = bundle.frames[i]
            af = AlignedFrame(
                frame=f,
                visibility="future",
                available_modalities=_available_modalities(bundle, f),
            )
            future_frames.append(af)

        input_frames = tuple(observed_frames) + (current_aligned,)

        # Resolve SDC identity
        sdc_track_index = bundle.sdc_track_index
        sdc_track_id = None
        if sdc_track_index is not None:
            for agent in current_frame.agent_states:
                if agent.track_index == sdc_track_index and agent.valid:
                    sdc_track_id = agent.track_id
                    break
            if sdc_track_id is None:
                raise AlignmentError(
                    f"sdc_track_index={sdc_track_index} not found in current frame agents"
                )

        return AlignmentContext(
            scenario_id=bundle.scenario_id,
            watermark=watermark,
            observed_frames=tuple(observed_frames),
            current_frame=current_aligned,
            future_frames=tuple(future_frames),
            input_frames=input_frames,
            source=bundle.source,
            map_features=bundle.map_features,
            sdc_track_index=sdc_track_index,
            sdc_track_id=sdc_track_id,
            available_capabilities=bundle.available_capabilities,
            data_source_metadata=bundle.metadata,
        )

    def align_full_scene(self, bundle: ScenarioBundle) -> AlignmentContext:
        if not bundle.frames:
            raise AlignmentError("bundle.frames must not be empty")

        watermark_frame = bundle.frames[-1]
        watermark = Watermark(
            scenario_id=bundle.scenario_id,
            step_index=watermark_frame.step_index,
            timestamp_seconds=watermark_frame.timestamp_seconds,
        )

        input_frames = tuple(
            AlignedFrame(
                frame=replace(frame, phase="current"),
                visibility="current",
                available_modalities=_available_modalities(bundle, frame),
            )
            for frame in bundle.frames
        )

        sdc_track_index = bundle.sdc_track_index
        sdc_track_id = None
        if sdc_track_index is not None:
            for frame in bundle.frames:
                for agent in frame.agent_states:
                    if agent.track_index == sdc_track_index and agent.valid:
                        sdc_track_id = agent.track_id
                        break
                if sdc_track_id is not None:
                    break
            if sdc_track_id is None:
                raise AlignmentError(
                    f"sdc_track_index={sdc_track_index} not found in scene agents"
                )

        return AlignmentContext(
            scenario_id=bundle.scenario_id,
            watermark=watermark,
            observed_frames=(),
            current_frame=input_frames[-1],
            future_frames=(),
            input_frames=input_frames,
            source=bundle.source,
            map_features=bundle.map_features,
            sdc_track_index=sdc_track_index,
            sdc_track_id=sdc_track_id,
            available_capabilities=bundle.available_capabilities,
            data_source_metadata=bundle.metadata,
            evaluation_mode="offline_full_scene",
        )
