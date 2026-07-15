# Downstream Contracts

TriggerEngine, NeuralSceneBridge, and ClosedLoopBench are separate projects with explicit handoff contracts. There is no required top-level orchestrator. Each project owns its deliverable and can be developed by a different team.

## Project Roles

```text
TriggerEngine
  real logs -> mined high-value events -> Scenario IR

NeuralSceneBridge
  scene token + dataset assets -> NuRec/Cosmos configs -> Reconstruction Package + Sim2Real Report

ClosedLoopBench
  Scenario IR + optional Reconstruction Package -> final Scene Package -> CARLA/ScenarioRunner config -> closed-loop report
```

## Source Of Truth

`Scenario IR` is the canonical internal representation between projects.

It is not intended to replace public standards. Instead, downstream adapters export public/runtime formats:

- `Scenario IR -> NuRec job config`
- `Scenario IR -> Cosmos variant config`
- `Scenario IR -> CARLA run config`
- `Scenario IR -> OpenSCENARIO .xosc`
- `Scenario IR -> minimal OpenDRIVE .xodr`

## Handoff Matrix

| Producer | Artifact | Consumer | Required | Purpose |
| --- | --- | --- | --- | --- |
| TriggerEngine | Scenario IR | NeuralSceneBridge | Yes | Reconstruction, Cosmos variants, sim-to-real evaluation |
| TriggerEngine | Scenario IR | ClosedLoopBench | Yes | CARLA scenario compilation and closed-loop metrics |
| NeuralSceneBridge | Reconstruction Package | ClosedLoopBench | Optional | NuRec/Cosmos visual realism hook |
| NeuralSceneBridge | Sim2Real Report | ClosedLoopBench / reviewer | Optional | Visual domain-gap evidence |
| ClosedLoopBench | Closed-loop Report | TriggerEngine / reviewer | Optional | Downstream validation of mined scenario families |

## Boundary Rules

TriggerEngine does not:

- run CARLA
- run NuRec/Cosmos
- own actor behavior models
- export simulator-specific formats as its primary interface

NeuralSceneBridge does not:

- own ego planning
- own actor policy
- advance closed-loop world state
- decide scenario risk semantics

ClosedLoopBench does not:

- mine raw logs
- reconstruct neural scenes
- train Cosmos/NuRec assets
- treat UniAD as the only ego policy

## MVP Handoff

MVP handoff for one nuScenes mini seed:

```text
TriggerEngine:
  outputs/scenario_ir/scene-1077.integrated.json

NeuralSceneBridge:
  outputs/scene-1077-integrated/reconstruction_package.json
  outputs/scene-1077-integrated/nurec_job_config.json
  outputs/scene-1077-integrated/cosmos_variant_config.json
  outputs/scene-1077-integrated/sim2real_report.json

ClosedLoopBench:
  outputs/scene-1077-integrated/carla_run_config.json
  outputs/scene-1077-integrated/scenario.xosc
  outputs/scene-1077-integrated/road.xodr
  outputs/scene-1077-integrated/closed_loop_report.json
```

## Final Handoff

The final system should keep the same ownership boundaries while making each adapter executable:

- TriggerEngine resolves richer dataset refs, camera samples, calibration, bbox tracks, lane graph, route, and conflict points.
- NeuralSceneBridge resolves real image/calibration assets, projects dynamic masks, runs NuRec/Cosmos Docker jobs, and computes image/perception gap metrics.
- ClosedLoopBench runs CARLA/ScenarioRunner, supports ego policy plugins, actor style templates, TrafficManager/scripted actors, per-tick metrics, and optional NuRec/Cosmos sensor paths.
