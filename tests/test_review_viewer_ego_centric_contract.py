from __future__ import annotations

import unittest

from tests.test_review_viewer_v2_contract import make_context_with_future_and_map, make_mixed_result


class ReviewViewerEgoCentricContractTests(unittest.TestCase):
    def test_pair_event_transform_is_ego_centered_and_ego_heading_aligned(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("function pairRoleIds", html)
        self.assertIn("function egoAgentForEvent", html)
        self.assertIn("function targetAgentForEvent", html)

        transform_start = html.index("function eventFrameTransform")
        transform_end = html.index("function worldToEventLocal", transform_start)
        transform_source = html[transform_start:transform_end]

        self.assertIn("egoAgentForEvent(event, frame)", transform_source)
        self.assertIn("cx: ego.x", transform_source)
        self.assertIn("cy: ego.y", transform_source)
        self.assertIn("heading: ego.heading", transform_source)
        self.assertNotIn("cx /= count", transform_source)
        self.assertNotIn("cy /= count", transform_source)

    def test_projection_uses_ego_anchor_with_more_forward_space(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        project_start = html.index("function project(")
        project_end = html.index("function featureIntersectsBounds", project_start)
        project_source = html[project_start:project_end]

        self.assertIn("transform.anchor", project_source)
        self.assertIn("anchor.x * canvas.width", project_source)
        self.assertIn("anchor.y * canvas.height", project_source)
        self.assertIn("y: 0.68", html)

    def test_role_rendering_uses_explicit_pair_order_not_set_iteration(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        role_start = html.index("function roleForAgent")
        role_end = html.index("function drawRoleBadge", role_start)
        role_source = html[role_start:role_end]

        self.assertIn("pairRoleIds(event)", role_source)
        self.assertIn("ids.egoId", role_source)
        self.assertIn("ids.targetId", role_source)

    def test_sdc_pair_events_use_the_same_ego_target_rendering_path(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        payload["events"][0]["subject_type"] = "sdc_pair"
        payload["review_events"][0]["subject_type"] = "sdc_pair"
        html = render_viewer_html(payload)

        pair_start = html.index("function isPairEvent")
        pair_end = html.index("function pairRoleIds", pair_start)
        pair_source = html[pair_start:pair_end]
        self.assertIn("event.subject_type === 'agent_pair'", pair_source)
        self.assertIn("event.subject_type === 'sdc_pair'", pair_source)

        summary_start = html.index("function updateEventSummary")
        summary_end = html.index("function updateSelectionDetails", summary_start)
        summary_source = html[summary_start:summary_end]
        self.assertIn("const ids = pairRoleIds(event)", summary_source)
        self.assertIn("summaryEgo.textContent = agentLabel", summary_source)
        self.assertIn("ids.egoId", summary_source)
        self.assertIn("summaryTarget.textContent = agentLabel", summary_source)
        self.assertIn("ids.targetId", summary_source)

    def test_canvas_backing_store_matches_rendered_size_to_avoid_misalignment(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("function resizeCanvasToDisplaySize", html)
        self.assertIn("canvas.clientWidth", html)
        self.assertIn("canvas.clientHeight", html)
        self.assertIn("window.devicePixelRatio", html)
        self.assertIn("resizeCanvasToDisplaySize()", html)
        self.assertIn("window.addEventListener('resize'", html)

    def test_ego_and_target_have_large_labels_and_distinct_outlines(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("drawRoleLabel", html)
        self.assertIn("drawEgoAnchor", html)
        self.assertIn("role === 'EGO' ? 4 : 3", html)
        self.assertIn("font = 'bold 13px system-ui'", html)
        self.assertIn("EGO", html)
        self.assertIn("TARGET", html)

    def test_viewer_layout_uses_full_available_width_inside_index_iframe(self):
        from tools.export_viewer import build_viewer_payload, render_viewer_html

        payload = build_viewer_payload(make_context_with_future_and_map(), make_mixed_result())
        html = render_viewer_html(payload)

        self.assertIn("max-width: 100vw", html)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 280px", html)
        self.assertIn("aspect-ratio: 16 / 9", html)
        self.assertIn("min-height: 520px", html)


if __name__ == "__main__":
    unittest.main()
