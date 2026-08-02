from __future__ import annotations

import math
from collections import defaultdict

from .frames import MapFeature, Point3D


_LANE_CENTERLINE_MIN_SAMPLES = 8
_LANE_CENTERLINE_MAX_SAMPLES = 32
_LANE_TOPOLOGY_MAX_GAP_M = 3.0
_LANE_TOPOLOGY_MAX_HEADING_DELTA_RAD = 0.7


def normalize_nuscenes_map(
    map_json: dict | None,
    origin: tuple[float, float, float],
) -> dict[int, MapFeature]:
    """Convert a nuScenes map expansion into the engine map contract."""
    if not map_json:
        return {}

    nodes = {row["token"]: row for row in map_json.get("node", [])}
    polygons = {row["token"]: row for row in map_json.get("polygon", [])}
    lines = {row["token"]: row for row in map_json.get("line", [])}
    features: dict[int, MapFeature] = {}
    next_id = 1

    def node_point(token: str) -> Point3D | None:
        node = nodes.get(token)
        if node is None:
            return None
        return Point3D(node["x"] - origin[0], node["y"] - origin[1], 0.0)

    def polygon_points(token: str) -> tuple[Point3D, ...]:
        polygon = polygons.get(token)
        if polygon is None:
            return ()
        points = [node_point(node_token) for node_token in polygon.get("exterior_node_tokens", [])]
        return tuple(point for point in points if point is not None)

    def line_points(token: str) -> tuple[Point3D, ...]:
        line = lines.get(token)
        if line is None:
            return ()
        points = [node_point(node_token) for node_token in line.get("node_tokens", [])]
        return tuple(point for point in points if point is not None)

    def add_polygon(
        feature_type: str,
        row: dict,
        polygon_token: str,
        properties: dict[str, object] | None = None,
        polyline: tuple[Point3D, ...] = (),
    ) -> int | None:
        nonlocal next_id
        points = polygon_points(polygon_token)
        if len(points) < 3:
            return None
        feature_id = next_id
        features[feature_id] = MapFeature(
            feature_id=feature_id,
            feature_type=feature_type,
            polyline=polyline,
            polygon=points,
            properties={
                "token": row.get("token", ""),
                **(properties or {}),
            },
        )
        next_id += 1
        return feature_id

    def add_line(
        feature_type: str,
        row: dict,
        line_token: str,
        properties: dict[str, object] | None = None,
    ) -> None:
        nonlocal next_id
        points = line_points(line_token)
        if len(points) < 2:
            return
        features[next_id] = MapFeature(
            feature_id=next_id,
            feature_type=feature_type,
            polyline=points,
            polygon=(),
            properties={
                "token": row.get("token", ""),
                **(properties or {}),
            },
        )
        next_id += 1

    for row in map_json.get("lane", []):
        centerline, centerline_source = _lane_centerline(
            row,
            polygons,
            lines,
            node_point,
        )
        add_polygon(
            "lane",
            row,
            row.get("polygon_token", ""),
            {
                "lane_type": row.get("lane_type", ""),
                "from_edge_line_token": row.get("from_edge_line_token", ""),
                "to_edge_line_token": row.get("to_edge_line_token", ""),
                "centerline_source": centerline_source,
            },
            polyline=centerline,
        )
    for row in map_json.get("road_segment", []):
        add_polygon(
            "road_segment",
            row,
            row.get("polygon_token", ""),
            {"is_intersection": row.get("is_intersection", False)},
        )
    for row in map_json.get("walkway", []):
        add_polygon("walkway", row, row.get("polygon_token", ""))
    for row in map_json.get("ped_crossing", []):
        add_polygon("ped_crossing", row, row.get("polygon_token", ""))
    for row in map_json.get("stop_line", []):
        add_polygon(
            "stop_line",
            row,
            row.get("polygon_token", ""),
            {"stop_line_type": row.get("stop_line_type", "")},
        )
    for row in map_json.get("road_divider", []):
        add_line("road_divider", row, row.get("line_token", ""))
    for row in map_json.get("lane_divider", []):
        add_line("lane_divider", row, row.get("line_token", ""))
    for row in map_json.get("drivable_area", []):
        for polygon_token in row.get("polygon_tokens", []):
            add_polygon("drivable_area", row, polygon_token)

    _annotate_lane_topology(features)
    return features


def _ring_path(
    ring_tokens: tuple[str, ...],
    start_index: int,
    end_index: int,
    step: int,
) -> tuple[str, ...]:
    path: list[str] = []
    index = start_index
    for _ in range(len(ring_tokens) + 1):
        path.append(ring_tokens[index])
        if index == end_index:
            return tuple(path)
        index = (index + step) % len(ring_tokens)
    return ()


def _resample_polyline(points: tuple[Point3D, ...], sample_count: int) -> tuple[Point3D, ...]:
    if len(points) < 2:
        return points

    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(
            cumulative[-1]
            + math.sqrt(
                (second.x - first.x) ** 2
                + (second.y - first.y) ** 2
                + (second.z - first.z) ** 2
            )
        )
    total_length = cumulative[-1]
    if total_length <= 1e-9:
        return (points[0], points[-1])

    result: list[Point3D] = []
    for sample_index in range(sample_count):
        target = total_length * sample_index / (sample_count - 1)
        segment_index = 0
        while (
            segment_index < len(cumulative) - 2
            and cumulative[segment_index + 1] < target
        ):
            segment_index += 1
        start = points[segment_index]
        end = points[segment_index + 1]
        segment_length = cumulative[segment_index + 1] - cumulative[segment_index]
        fraction = (
            (target - cumulative[segment_index]) / segment_length
            if segment_length > 1e-9
            else 0.0
        )
        result.append(
            Point3D(
                x=start.x + fraction * (end.x - start.x),
                y=start.y + fraction * (end.y - start.y),
                z=start.z + fraction * (end.z - start.z),
            )
        )
    return tuple(result)


def _midpoint(first: Point3D, second: Point3D) -> Point3D:
    return Point3D(
        x=(first.x + second.x) / 2.0,
        y=(first.y + second.y) / 2.0,
        z=(first.z + second.z) / 2.0,
    )


def _edge_midpoint_centerline(
    from_line: dict | None,
    to_line: dict | None,
    node_point,
) -> tuple[Point3D, ...]:
    if from_line is None or to_line is None:
        return ()
    from_points = tuple(
        point
        for point in (node_point(token) for token in from_line.get("node_tokens", ()))
        if point is not None
    )
    to_points = tuple(
        point
        for point in (node_point(token) for token in to_line.get("node_tokens", ()))
        if point is not None
    )
    if len(from_points) != 2 or len(to_points) != 2:
        return ()
    start = _midpoint(from_points[0], from_points[1])
    end = _midpoint(to_points[0], to_points[1])
    if (end.x - start.x) ** 2 + (end.y - start.y) ** 2 <= 1e-9:
        return ()
    return (start, end)


def _lane_centerline(
    row: dict,
    polygons: dict[str, dict],
    lines: dict[str, dict],
    node_point,
) -> tuple[tuple[Point3D, ...], str]:
    polygon = polygons.get(row.get("polygon_token", ""))
    from_line = lines.get(row.get("from_edge_line_token", ""))
    to_line = lines.get(row.get("to_edge_line_token", ""))
    fallback = _edge_midpoint_centerline(from_line, to_line, node_point)
    if polygon is None or from_line is None or to_line is None:
        return fallback, "edge_midpoint_fallback" if fallback else "unavailable"

    ring_tokens = tuple(polygon.get("exterior_node_tokens", ()))
    if len(ring_tokens) > 1 and ring_tokens[0] == ring_tokens[-1]:
        ring_tokens = ring_tokens[:-1]
    from_tokens = tuple(from_line.get("node_tokens", ()))
    to_tokens = tuple(to_line.get("node_tokens", ()))
    if (
        len(ring_tokens) < 4
        or len(from_tokens) != 2
        or len(to_tokens) != 2
        or any(token not in ring_tokens for token in (*from_tokens, *to_tokens))
    ):
        return fallback, "edge_midpoint_fallback" if fallback else "unavailable"

    from_indices = tuple(ring_tokens.index(token) for token in from_tokens)
    to_indices = tuple(ring_tokens.index(token) for token in to_tokens)
    first_boundary = _ring_path(ring_tokens, from_indices[0], to_indices[0], 1)
    second_boundary = _ring_path(ring_tokens, from_indices[1], to_indices[1], -1)
    from_points = tuple(
        point for point in (node_point(token) for token in from_tokens) if point is not None
    )
    to_points = tuple(
        point for point in (node_point(token) for token in to_tokens) if point is not None
    )
    if (
        not first_boundary
        or not second_boundary
        or len(first_boundary) < 2
        or len(second_boundary) < 2
        or len(from_points) != 2
        or len(to_points) != 2
    ):
        return fallback, "edge_midpoint_fallback" if fallback else "unavailable"

    start = _midpoint(from_points[0], from_points[1])
    end = _midpoint(to_points[0], to_points[1])

    def boundary_points(tokens: tuple[str, ...]) -> tuple[Point3D, ...]:
        points = tuple(
            point for point in (node_point(token) for token in tokens) if point is not None
        )
        if len(points) < 2:
            return ()
        return (start, *points[1:-1], end)

    first_points = boundary_points(first_boundary)
    second_points = boundary_points(second_boundary)
    if len(first_points) < 2 or len(second_points) < 2:
        return fallback, "edge_midpoint_fallback" if fallback else "unavailable"

    sample_count = max(
        _LANE_CENTERLINE_MIN_SAMPLES,
        min(_LANE_CENTERLINE_MAX_SAMPLES, max(len(first_points), len(second_points))),
    )
    first_resampled = _resample_polyline(first_points, sample_count)
    second_resampled = _resample_polyline(second_points, sample_count)
    centerline = tuple(
        _midpoint(first, second)
        for first, second in zip(first_resampled, second_resampled)
    )
    if len(centerline) < 2:
        return fallback, "edge_midpoint_fallback" if fallback else "unavailable"
    return centerline, "polygon_boundary_midpoint"


def _angle_delta(first: float, second: float) -> float:
    delta = abs(first - second)
    if delta > math.pi:
        delta = 2 * math.pi - delta
    return delta


def _polyline_heading(polyline: tuple[Point3D, ...], *, from_start: bool) -> float | None:
    pairs = (
        zip(polyline, polyline[1:])
        if from_start
        else zip(reversed(polyline[:-1]), reversed(polyline[1:]))
    )
    for first, second in pairs:
        dx = second.x - first.x
        dy = second.y - first.y
        if dx * dx + dy * dy > 1e-9:
            return math.atan2(dy, dx)
    return None


def _annotate_lane_topology(features: dict[int, MapFeature]) -> int:
    lanes = [
        feature
        for feature in features.values()
        if feature.feature_type == "lane" and feature.polyline
    ]
    starts_by_cell: dict[tuple[int, int], list[MapFeature]] = defaultdict(list)
    cell_size = _LANE_TOPOLOGY_MAX_GAP_M
    for lane in lanes:
        start = lane.polyline[0]
        cell = (math.floor(start.x / cell_size), math.floor(start.y / cell_size))
        starts_by_cell.setdefault(cell, []).append(lane)

    entry_lanes: dict[int, set[int]] = {lane.feature_id: set() for lane in lanes}
    exit_lanes: dict[int, set[int]] = {lane.feature_id: set() for lane in lanes}
    link_count = 0
    for lane in lanes:
        end = lane.polyline[-1]
        end_heading = _polyline_heading(lane.polyline, from_start=False)
        if end_heading is None:
            continue
        cell_x = math.floor(end.x / cell_size)
        cell_y = math.floor(end.y / cell_size)
        for offset_x in (-1, 0, 1):
            for offset_y in (-1, 0, 1):
                for successor in starts_by_cell.get(
                    (cell_x + offset_x, cell_y + offset_y), ()
                ):
                    if successor.feature_id == lane.feature_id:
                        continue
                    start = successor.polyline[0]
                    distance = math.sqrt(
                        (end.x - start.x) ** 2 + (end.y - start.y) ** 2
                    )
                    start_heading = _polyline_heading(
                        successor.polyline, from_start=True
                    )
                    if (
                        distance > _LANE_TOPOLOGY_MAX_GAP_M
                        or start_heading is None
                        or _angle_delta(end_heading, start_heading)
                        > _LANE_TOPOLOGY_MAX_HEADING_DELTA_RAD
                    ):
                        continue
                    if successor.feature_id in exit_lanes[lane.feature_id]:
                        continue
                    exit_lanes[lane.feature_id].add(successor.feature_id)
                    entry_lanes[successor.feature_id].add(lane.feature_id)
                    link_count += 1

    for lane in lanes:
        properties = dict(lane.properties or {})
        properties["entry_lanes"] = tuple(sorted(entry_lanes[lane.feature_id]))
        properties["exit_lanes"] = tuple(sorted(exit_lanes[lane.feature_id]))
        properties["topology_source"] = "endpoint_heading_inferred"
        features[lane.feature_id] = MapFeature(
            feature_id=lane.feature_id,
            feature_type=lane.feature_type,
            polyline=lane.polyline,
            polygon=lane.polygon,
            properties=properties,
        )
    return link_count
