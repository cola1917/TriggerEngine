# Engine Review Intent Worker Tasks

## Objective

Move review/supporting/debug semantics from viewer hard-coded tag lists into
rule and engine metadata.

The viewer may keep tag-name fallback for backward compatibility, but new engine
events must carry explicit intent in `TagEvent.metadata["intent"]`.

## Current Failing Tests

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_engine_review_intent_contract -v
```

Expected failures before implementation:

- `test_parser_accepts_emit_intent_and_defaults_to_debug`
- `test_parser_rejects_unknown_emit_intent`
- `test_single_frame_engine_copies_intent_into_tag_event_metadata`
- `test_temporal_engine_copies_intent_into_tag_event_metadata`
- `test_viewer_export_prefers_event_metadata_intent_over_tag_name_fallback`

## Required Changes

### 1. Rule AST

Update `trigger_engine/rules/ast.py`:

- add `intent: str = "debug"` to `RuleEmit`
- allowed intents are:
  - `review`
  - `supporting`
  - `debug`

Do not change `TagEvent` schema in this phase.

### 2. Rule Parser

Update `trigger_engine/rules/parser.py`:

- parse `emit.intent`
- default missing `emit.intent` to `debug`
- reject unknown intent with `RuleParseError` mentioning `intent`
- keep existing `emit.metadata`, `emit.policy`, and `emit.value` behavior

Important: current YAML uses `emit:`, not `emits:`.

### 3. Single-Frame Rule Engine

Update `trigger_engine/rules/engine.py`:

- merge `rule.emit.metadata` into emitted event metadata
- always add `intent: rule.emit.intent`
- preserve existing metadata:
  - `rule_kind`
  - `operator_results`

Recommended merge order:

```python
metadata = dict(rule.emit.metadata)
metadata.update({
    "intent": rule.emit.intent,
    "rule_kind": "single_frame",
    "operator_results": operator_results,
})
```

### 4. Temporal Rule Engine

Update `trigger_engine/engine/trigger_engine.py`:

- in temporal event construction, merge `rule.emit.metadata`
- always add `intent: rule.emit.intent`
- preserve temporal metadata:
  - `rule_kind`
  - `temporal_kind`
  - `source_tag` / `source_tags`
  - supporting frames and timestamps
  - window fields

Recommended: merge in `_build_temporal_event(...)` so both sustained and
sequence rules share behavior.

### 5. Viewer Export Classification

Update `tools/export_viewer.py`:

- `classify_event_group(event)` should prefer `event.metadata["intent"]`
- mapping:
  - `review` -> `primary`
  - `supporting` -> `supporting`
  - `debug` -> `debug`
- if metadata intent is absent, keep current tag-name fallback
- if metadata intent is unknown, treat as `debug`

This keeps old payloads compatible while moving new semantics to engine output.

### 6. Classic Scenario Rules

Update `trigger_engine/scenarios/classic.py` YAML:

- review:
  - `cut_in_confirmed`
  - `cut_in_risk`
  - `low_ttc_pair`
  - `persistent_low_ttc_pair`
  - `red_light_running`
- supporting:
  - `adjacent_vehicle`
  - `cut_in_lateral_approach`
  - `same_path_overlap`
  - `red_light_stop_line_approach`
  - `red_light_stop_line_crossed`
- debug:
  - `vehicle_stopped`
  - `vehicle_stopped_for_3_frames`
  - `vehicle_stopped_at_red`

If a listed tag is not present in current classic rules, skip it.

## Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_engine_review_intent_contract -v
.\.venv\Scripts\python.exe -m unittest tests.test_review_viewer_v2_contract -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Real-data verification:

```powershell
$env:PYTHONPATH='E:\code\TriggerEngine\third_party'
.\.venv\Scripts\python.exe tools\export_review_payload.py data\validation_interactive.tfrecord-00000-of-00150 -o review_payload.json --scenario-index 0 --map-feature-limit 300 --future-frames 30 --map-crop-margin-m 80
.\.venv\Scripts\python.exe tools\render_viewer.py review_payload.json -o viewer.html
.\.venv\Scripts\python.exe -c "import json,collections; p=json.load(open('review_payload.json',encoding='utf-8')); print(collections.Counter(p['events'][i]['tag_name'] for i in p['review_event_indices'])); print(collections.Counter(e.get('metadata',{}).get('intent') for e in p['events']))"
```

Expected current real-data review tags:

```text
{'cut_in_confirmed': 1}
```

## Acceptance

- Engine events carry `metadata.intent`.
- Viewer export uses metadata intent first.
- Tag-name fallback still works for old/manual events.
- Real-data default review remains high-value only.
