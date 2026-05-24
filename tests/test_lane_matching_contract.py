import math
import unittest

from trigger_engine.alignment.context import AlignedFrame, AlignmentContext, Watermark
from trigger_engine.data.frames import Frame
from trigger_engine.data.frames import AgentState, MapFeature, Point3D


def agent(x=0.0, y=0.0, heading=0.0):
    return AgentState(
        track_id=1,
        track_index=1,
        object_type="vehicle",
        timestamp_seconds=0.0,
        center=Point3D(x, y, 0.0),
        velocity_x=8.0,
        velocity_y=0.0,
        heading=heading,
        length=4.0,
        width=1.8,
        height=1.5,
        valid=True,
    )


def lane(feature_id, points):
    return MapFeature(
        feature_id=feature_id,
        feature_type="lane",
        polyline=tuple(Point3D(x, y, 0.0) for x, y in points),
        polygon=(),
        properties={},
    )


class LaneMatchingContractTests(unittest.TestCase):
    def test_matcher_prefers_aligned_lane_over_closer_misaligned_lane(self):
        from trigger_engine.operators.lane_matching import match_agent_to_lane

        misaligned_heading = 0.5
        dx, dy = math.cos(misaligned_heading), math.sin(misaligned_heading)
        match = match_agent_to_lane(
            agent(),
            {
                10: lane(10, [(-10.0 * dx, -10.0 * dy), (10.0 * dx, 10.0 * dy)]),
                11: lane(11, [(-10.0, 0.6), (10.0, 0.6)]),
            },
            max_lateral_m=1.5,
            max_heading_delta_rad=0.7,
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.lane_id, 11)

    def test_cached_match_reuses_context_result_without_changing_match(self):
        from trigger_engine.operators.lane_matching import (
            match_agent_to_lane,
            match_agent_to_lane_cached,
        )

        ego = agent()
        map_features = {
            11: lane(11, [(-10.0, 0.6), (10.0, 0.6)]),
        }
        frame = AlignedFrame(
            frame=Frame(
                scenario_id="lane-cache",
                step_index=0,
                timestamp_seconds=0.0,
                phase="current",
                agent_states=(ego,),
                traffic_lights=(),
            ),
            visibility="current",
            available_modalities=frozenset({"agents", "map"}),
        )
        context = AlignmentContext(
            scenario_id="lane-cache",
            watermark=Watermark("lane-cache", 0, 0.0),
            observed_frames=(),
            current_frame=frame,
            future_frames=(),
            input_frames=(frame,),
            map_features=map_features,
            sdc_track_id=1,
        )

        expected = match_agent_to_lane(
            ego,
            map_features,
            max_lateral_m=1.5,
            max_heading_delta_rad=0.7,
        )
        first = match_agent_to_lane_cached(
            context,
            ego,
            map_features,
            max_lateral_m=1.5,
            max_heading_delta_rad=0.7,
        )
        second = match_agent_to_lane_cached(
            context,
            ego,
            map_features,
            max_lateral_m=1.5,
            max_heading_delta_rad=0.7,
        )

        self.assertEqual(first, expected)
        self.assertIs(second, first)
        self.assertEqual(len(context.lane_match_cache), 1)
        self.assertEqual(len(context.lane_match_index_cache), 1)

    def test_segment_index_finds_lane_when_agent_is_near_long_segment(self):
        from trigger_engine.operators.lane_matching import match_agent_to_lane

        match = match_agent_to_lane(
            agent(x=95.0, y=0.8),
            {
                20: lane(20, [(0.0, 0.0), (100.0, 0.0)]),
            },
            max_lateral_m=1.0,
            max_heading_delta_rad=0.7,
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.lane_id, 20)
        self.assertAlmostEqual(match.longitudinal_s_m, 95.0)


if __name__ == "__main__":
    unittest.main()
