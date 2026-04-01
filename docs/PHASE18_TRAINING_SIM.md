# S3M Phase 18 — Layer 12 Training & Simulation Advanced

## Overview
Phase 18 extends Phase 7 simulation into a full officer education and wargaming stack with LLM-assisted adversaries, structured exercises, scenario authoring, and training portal analytics.

## Architecture
- **Wargaming Suite** (`apps/simulation/wargaming/`):
  - `LLMAdversary`: profile-driven red-force commander (Grok domain routing with scripted fallback).
  - `TurnResolver`: maneuver + combat resolution (terrain, ambush, fortification, losses, victory checks).
  - `WargameEngine`: session lifecycle (create/start/orders/complete/AAR).
  - `WargameSuite`: quick demos, COA runs, ORBAT-origin sessions, statistics.
- **Exercise Framework** (`apps/simulation/exercises/`):
  - `ExerciseBuilder`: tabletop/command-post/cyber templates.
  - `ExerciseEvaluator`: weighted score model and grading.
  - `ExerciseFramework`: exercise store + evaluation orchestration.
- **Training Portal** (`apps/simulation/training/`):
  - `OfficerManager`, `CourseManager`, `AssignmentTracker`, `TrainingPortal`.
- **Scenario Authoring** (`apps/simulation/scenario_author.py`):
  - ORBAT-based generation, NL brief generation, MSDL conversion, template catalog.
- **Battle Visualization** (`apps/simulation/battle_visualizer.py`):
  - Turn frame generation, replay export, summary map data.
- **Cyber Range Integration** (`apps/simulation/cyber_range.py`):
  - Integrates Phase 13 `CyberTrainingManager` workflows.
- **Manager** (`apps/simulation/manager.py`):
  - `TrainingSimManager` unifies all Layer 12 operations.

## LLM Adversary
- Profiles: Competent Adversary, Insurgent Commander, Peer Navy Admiral, Cyber APT Group, Swarm Tactician.
- Difficulty behaviors: novice, competent, expert, grandmaster.
- Offline-safe fallback ensures deterministic order generation when LLM output is unavailable/unparseable.

## Engagement Model
Turn resolution computes:
1. Movement and maneuver updates.
2. Engagement strengths from `size × condition × terrain` (+ambush / fortification modifiers).
3. Ratio outcomes:
   - >3:1 defender destroyed
   - 2:1–3:1 defender heavily damaged
   - 1:1–2:1 both damaged
   - <1:1 attacker damaged
4. Recon detections and event timeline.
5. Victory checks against configured conditions.

## Wargame Lifecycle
`WargameConfig -> WargameSession -> submit orders -> WargameTurn[] -> WargameResult -> AAR`

## Exercise Evaluation
Weighted scoring per phase:
- Objectives met: 40%
- Wargame performance: 30%
- Timeliness: 15%
- Decision quality: 15%

Grades:
- A+ (95+), A (85+), B+ (75+), B (65+), C (55+), F (<55)

## Training Portal
Tracks:
- Officer records and readiness scores
- Course catalog and prerequisites
- Assignment lifecycle and completion stats
- Certification progress

## Standard Courses
1. Combined Arms Wargaming
2. Cyber Defense Operations
3. Maritime Domain Awareness
4. Autonomous Systems Command
5. Coalition Operations

## Scenario Authoring
Supports:
- ORBAT-to-scenario
- Natural language brief-to-scenario
- MSDL XML import/export
- Five templates: Desert Patrol, Urban Assault, Naval Blockade, Air Defense, Cyber+Kinetic Hybrid

## Integration
- **Phase 7:** Scenario engine and simulation foundation
- **Phase 13:** Cyber training exercises and SOC workflows
- **Phase 16 equivalent interop layer:** DIS/C2SIM-style exercise workflow integration

## API Endpoints
Layer 12 routes are defined in `src/api/training_sim_routes.py` and mounted in `src/api/server.py` under tag **Training & Simulation Advanced**.

## Configuration
`configs/training-simulation.yaml` defines default turn limits, engagement modifiers, evaluation weights, grading thresholds, and visualization controls.

## Future Direction
Phase 19 focus: Intelligence & OSINT fusion into exercise injects and adaptive scenario generation.
