# Review Viewer Directory Index Worker Tasks

## Assignment

Implement a static directory-level `view.html` for review payload outputs.

The reviewer should open one HTML file, see all JSON payloads in the output
directory that have review-level events, choose one, and inspect it through the
existing single-scenario viewer.

Design:

- `docs/review_viewer_directory_index_plan.md`

## Checklist

- [x] Add `build_review_payload_index(payload_dir)` to `tools/export_viewer.py`.
- [x] Add `render_review_index_html(index)` to `tools/export_viewer.py`.
- [x] Add `render_review_index_from_payload_dir(payload_dir, output, viewer_dir=None)` to `tools/export_viewer.py`.
- [x] Add `tools/render_review_index.py` CLI wrapper.
- [x] Render per-payload viewer HTML only for files that have review events.
- [x] Keep `render_viewer.py` and `render_viewer_from_payload` single-payload behavior backward compatible.
- [x] Keep the index frontend review-only; do not run the engine or parse rules.
- [x] Make relative iframe paths work when opening `view.html` directly from disk.
- [x] Update or add tests until the new contract passes.

## Expected Review File Detection

A payload should appear in the index when either is true:

- `review_event_indices` is non-empty.
- `review_events` is non-empty.

Files with only debug/supporting events should not appear.

## Test Commands

Targeted red test:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_review_viewer_directory_index_contract -v
```

Regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_export_viewer_contract tests.test_review_viewer_v2_contract -v
```

Full suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Real-Data Check

After implementation, render the current bulk payload directory:

```powershell
.\.venv\Scripts\python.exe tools\render_review_index.py review_payload_bulk -o view.html
```

Expected direction from the latest accepted 100-file run:

- `payload_files`: 100
- `review_events`: 21
- review files should be the subset with high-value review tags such as
  `persistent_low_ttc_pair`, `cut_in_risk`, and `sdc_repeated_lane_change`.

The exact review file count can change if payloads are regenerated, but the
index must not show debug-only files.
