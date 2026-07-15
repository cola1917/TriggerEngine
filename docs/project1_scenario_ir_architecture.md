# Project 1: TriggerEngine / Scenario IR Architecture

## Goal

TriggerEngine is Project 1 in the scenario toolchain. Its job is to mine high-value driving situations from offline datasets, tag risk, select useful temporal windows, and export a simulator-agnostic Scenario IR that downstream projects can consume.

The design goal is deliberately narrow: TriggerEngine should produce a canonical internal representation that is easy to explain in interviews and stable enough for downstream adapters to build against. It should not become a simulator runtime, a reconstruction orchestrator, or a CARLA scenario authoring tool.

The concrete contract is tracked in [scenario_ir_contract.md](scenario_ir_contract.md). This document describes the architecture boundary and handoff model around that contract.

## System Boundary

TriggerEngine owns:

- Mining candidate scenarios from nuScenes and future offline datasets.
- Risk tagging through rules, operators, temporal policies, and scenario packs.
- Window selection around the trigger event, including event, warmup, and reconstruction windows.
- Scenario IR export with ego/actor reference trajectories, trigger metadata, risk metrics, data requirements, and dataset references.

TriggerEngine does not own:

- NuRec or Cosmos execution.
- CARLA execution.
- OpenSCENARIO or OpenDRIVE generation.
- Closed-loop ego policy execution.
- Neural reconstruction package metrics.
- Simulator-specific actor behavior implementation.

Those responsibilities live behind downstream adapters:

- NeuralSceneBridge converts `Scenario IR -> NuRec/Cosmos reconstruction package`.
- ClosedLoopBench converts `Scenario IR -> CARLA / ScenarioRunner closed-loop benchmark`.

```text
Offline dataset
  -> TriggerEngine mining and risk tagging
  -> Scenario IR canonical export
  -> NeuralSceneBridge adapter
       -> NuRec / Cosmos reconstruction package
  -> ClosedLoopBench adapter
       -> CARLA / ScenarioRunner scenario
```

## Scenario IR Positioning

Scenario IR is the canonical internal representation for this project family. It is not a replacement for OpenSCENARIO, OpenDRIVE, CARLA ScenarioRunner XML/Python, NuRec job files, or Cosmos configuration.

The distinction matters:

- Scenario IR preserves mined evidence from the source dataset.
- Scenario IR names the trigger, windows, participants, required data, and risk context.
- Scenario IR stays simulator-agnostic so that one mined scenario can feed multiple downstream consumers.
- Downstream adapters own lossy conversion decisions, such as map format mapping, actor policy translation, sensor rig packaging, and simulator-specific parameter defaults.

In interview terms: TriggerEngine decides "what scenario is worth testing and what evidence defines it"; downstream systems decide "how to reconstruct or execute it."

## MVP Contract

The frozen schema is `scenario_ir.v1` and is defined by the contract tests and [scenario_ir_contract.md](scenario_ir_contract.md).

MVP fields must cover:

- `windows`: `event`, `warmup`, and `reconstruction` time intervals.
- `ego.reference_trajectory`: source-dataset ego trajectory over the reconstruction window.
- `actors[*].reference_trajectory`: source-dataset actor tracks over the reconstruction window.
- `events.trigger`: selected trigger event with rule, time, subject, and metadata.
- `risk_metrics`: compact cross-project ranking and smoke-check summary.
- `data_requirements`: explicit reconstruction and closed-loop prerequisites.
- `dataset_refs`: source dataset lookup context without inlining dataset-specific records.

MVP interpretation:

- Reference trajectories are observed behavior, not counterfactual truth.
- `events.trigger` is the anchor for evaluation and window selection.
- `windows.event` is the closed-loop evaluation slice.
- `windows.warmup` initializes policies before evaluation.
- `windows.reconstruction` is wider than the event window so NeuralSceneBridge has enough evidence for reconstruction packaging.
- `dataset_refs.sample_refs` and `dataset_refs.index_refs` may remain deferred until the final contract promotes concrete sample or frame pointers.

## Final Contract

The final contract should extend the MVP without changing the core boundary. TriggerEngine still exports canonical Scenario IR; downstream adapters still perform simulator-specific conversion.

Final fields should add:

- Camera sample references for image-backed reconstruction.
- Camera calibration and sensor rig records.
- 2D/3D bounding-box tracks where available.
- Lane graph, route, and conflict point semantics.
- Scenario family parameters, such as cut-in gap, actor offset, occlusion distance, or traffic-light phase.
- Richer risk metrics, such as min TTC, gap, braking severity, route progress, and comfort statistics.
- Actor behavior template hints for closed-loop replay, scripted, or reactive policies.
- Links to downstream reconstruction packages when those artifacts are produced.

Future additions should be additive wherever possible. If a field must change semantics, the schema version must advance rather than mutating `scenario_ir.v1`.

## Downstream Handoff

| Consumer | Consumed MVP fields | Final fields expected | Responsibility |
| --- | --- | --- | --- |
| NeuralSceneBridge | `scenario_id`, `scenario_type`, `source`, `coordinate_frame`, `windows.reconstruction`, `ego.reference_trajectory`, `actors[*].reference_trajectory`, `actors[*].role`, `map_context`, `sensors.available_capabilities`, `data_requirements.reconstruction`, `dataset_refs` | camera sample refs, calibration, sensor rig, bbox tracks, reconstruction package links, scenario family parameters | Resolve dataset records, build NuRec/Cosmos inputs, generate masks/configs, report reconstruction package readiness. |
| ClosedLoopBench | `scenario_id`, `scenario_type`, `coordinate_frame`, `windows.event`, `windows.warmup`, `ego.initial_state`, `ego.reference_trajectory`, `actors[*].initial_state`, `actors[*].reference_trajectory`, `actors[*].policy_hints`, `events.trigger`, `risk_metrics`, `map_context`, `data_requirements.closed_loop`, `evaluation`, `variants` | lane graph, route, conflict points, actor behavior templates, rich risk metrics, scenario family parameter ranges | Convert to CARLA/ScenarioRunner assets, initialize ego and actors, run closed-loop policies, compute benchmark metrics. |

## Architecture Interfaces

### Inputs

TriggerEngine accepts normalized offline dataset bundles and rule configuration. Dataset adapters may read nuScenes or future datasets, but the core mining path should reason over normalized frames, agents, map context, and emitted `TagEvent` records.

### Processing

The Project 1 processing path is:

1. Normalize source frames into TriggerEngine data structures.
2. Run scenario packs and rule policies to emit `TagEvent` records.
3. Select the trigger event for export.
4. Derive event, warmup, and reconstruction windows.
5. Export ego and actor reference trajectories inside the reconstruction window.
6. Attach risk metrics, data requirements, dataset references, map context, sensor capability context, evaluation hints, and variant hints.

### Outputs

The primary output is Scenario IR JSON. Simulator-specific outputs are explicitly secondary and should be produced by downstream adapters rather than by TriggerEngine itself.

## Versioning Rules

- `scenario_ir.v1` is the current frozen cross-project schema version.
- Field additions may be introduced as optional final-contract candidates.
- Breaking semantic changes require a new schema version.
- Contract tests should pin required MVP behavior before implementation expands.
- Documentation should link back to [scenario_ir_contract.md](scenario_ir_contract.md) whenever field-level details are needed.

## Acceptance Criteria

- TriggerEngine's Project 1 boundary is explainable as mining, risk tagging, window selection, and Scenario IR export.
- Scenario IR is documented as canonical internal representation, not an OpenSCENARIO/OpenDRIVE replacement.
- MVP contract fields are clear enough for NeuralSceneBridge and ClosedLoopBench to start adapters.
- Final contract fields are identified without forcing them into MVP.
- Downstream handoff responsibilities are explicit and simulator-specific execution remains outside TriggerEngine.
- `tests.test_scenario_ir_contract` passes.
