# Review Viewer Directory Index Plan

## Goal

`view.html` should become a review entry point for a payload output directory,
not a one-scenario-only page. The reviewer should open one static HTML file,
see every payload file that contains review-level events, select a file, and
inspect that scenario in the existing single-scenario viewer.

This is a frontend review feature only. It must not run the engine, parse rules,
or regenerate payload JSON.

## Current Boundary

Existing flow:

```text
engine/export -> review_payload_*.json -> tools/render_viewer.py -> viewer.html
```

New flow:

```text
engine/export -> review_payload_*.json
              -> tools/render_review_index.py
              -> view.html + per-payload viewer html files
```

The payload JSON remains the backend/frontend boundary.

## Definitions

Review-level file:

- A payload JSON with non-empty `review_event_indices`, or
- a payload JSON with non-empty `review_events`.

Non-review files are hidden from the index by default. They can stay on disk,
but the reviewer should not have to see stopped/debug/supporting-only payloads.

## Proposed Components

### `build_review_payload_index(payload_dir)`

Add to `tools/export_viewer.py`.

Input:

- `payload_dir: Path`

Behavior:

- Scan `*.json` in filename order.
- Parse each file as a review payload.
- Count total payload files scanned.
- Include only files with review-level events.
- Extract compact metadata without loading those payloads in the browser.
- Skip invalid JSON with diagnostics instead of failing the whole index.

Output shape:

```json
{
  "payload_dir": "review_payload_bulk",
  "files": [
    {
      "file": "review_payload_00035.json",
      "path": "review_payload_00035.json",
      "viewer_path": "review_viewers/review_payload_00035.html",
      "scenario_id": "scenario-id",
      "source": "data/validation_interactive.tfrecord-00035-of-00150",
      "review_event_count": 1,
      "review_tag_counts": {
        "cut_in_risk": 1
      },
      "review_tags": ["cut_in_risk"],
      "first_review_frame_index": 8,
      "first_review_timestamp_seconds": 0.8,
      "total_events": 7
    }
  ],
  "stats": {
    "payload_files": 100,
    "review_files": 14,
    "review_events": 21
  },
  "diagnostics": []
}
```

Notes:

- `viewer_path` is filled by the directory renderer, not by the pure scanner,
  unless a caller passes a viewer path mapping.
- `review_tags` should be sorted for stable UI/tests.
- `first_review_*` comes from the first review event in payload review order.

### `render_review_index_html(index)`

Add to `tools/export_viewer.py`.

Behavior:

- Render one static HTML index page.
- Embed only the small index JSON, not every full payload.
- Left side: selectable review files.
- Right side: iframe showing the selected per-payload viewer HTML.
- Select the first review file by default.
- Empty state if no review files exist.

Required DOM contract:

- `id="reviewFileIndex"` JSON script tag.
- `id="reviewFileList"` file selector container.
- `id="viewerFrame"` iframe.
- `data-file="..."` on each selectable file row.

The index page should stay compact. The existing scenario viewer is already the
place for map playback and event details.

### `render_review_index_from_payload_dir(payload_dir, output, viewer_dir=None)`

Add to `tools/export_viewer.py`.

Behavior:

1. Build the review payload index.
2. Render one single-scenario viewer HTML per review payload by reusing
   `render_viewer_from_payload`.
3. Write the index HTML to `output`.
4. Return the final index dictionary or output path consistently.

Defaults:

- If `viewer_dir` is omitted, write per-payload viewers into
  `<output parent>/review_viewers`.
- `viewer_path` in the index should be relative to the index HTML directory so
  the static file works when opened locally.

### `tools/render_review_index.py`

Add a tiny CLI wrapper:

```powershell
.\.venv\Scripts\python.exe tools\render_review_index.py review_payload_bulk -o view.html
```

Optional:

```powershell
.\.venv\Scripts\python.exe tools\render_review_index.py review_payload_bulk -o view.html --viewer-dir review_viewers
```

## UI Behavior

- Header shows `review_files / payload_files` and total review events.
- File rows show:
  - file name
  - scenario id
  - review tags and counts
  - first review frame/time
- Selecting a row updates the iframe `src`.
- Keyboard/detail polish is optional for this version.

## Non-Goals

- Do not redesign the per-scenario canvas viewer in this task.
- Do not add backend execution controls to the page.
- Do not show debug/supporting-only files in the file list.
- Do not require a local web server.

## Acceptance

- The index includes only payload files with review-level events.
- The reviewer can switch between review files from one `view.html`.
- Existing single-payload viewer rendering still works.
- Existing viewer tests remain green.
