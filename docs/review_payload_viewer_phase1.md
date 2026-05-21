# Review Payload Viewer Phase 1

This phase separates offline data generation from static frontend review.

## Responsibility Boundary

Offline backend:

- reads TFRecord
- runs adapter, alignment, and TriggerEngine
- exports stable review payload JSON

Static frontend:

- reads review payload JSON
- renders BEV canvas
- filters tags
- jumps between events and frames
- shows event metadata for manual review

The frontend does not read TFRecord, run rules, or initialize the engine.

## Payload Contract

`review_payload.json` is the boundary between backend and frontend:

```json
{
  "scenario_id": "...",
  "source": "...",
  "plan_id": "classic_v1",
  "watermark": {},
  "frames": [],
  "events": [],
  "map_features": [],
  "stats": {},
  "diagnostics": []
}
```

## Commands

Export review data:

```powershell
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00000-of-00150 -o review_payload.json --scenario-index 0
```

Render static viewer from payload:

```powershell
.\.venv\Scripts\python.exe tools\render_viewer.py review_payload.json -o viewer.html
```

One-shot demo command remains available:

```powershell
.\.venv\Scripts\python.exe tools\export_viewer.py data\validation_interactive.tfrecord-00000-of-00150 -o viewer.html --scenario-index 0
```

## Review Flow

1. Batch or single-scenario backend export creates payloads.
2. Reviewer opens the static viewer.
3. Reviewer filters by tag and inspects frames/supporting frames.
4. Rule thresholds are adjusted based on observed false positives/negatives.
