# S3M Phase 7 — Simulation & Wargaming (Layer 04)

## Overview

Layer 04 provides an air-gapped, edge-friendly simulation and wargaming capability for tactical AI validation on NVIDIA Jetson AGX Orin.

Primary goals:
- Train and stress-test autonomy logic against synthetic adversaries.
- Generate reproducible tactical replays for commander debriefs.
- Produce synthetic datasets for threat detection and navigation validation.

High-level data flow:

```text
Layer 03 (Autonomy) ──> Layer 04 (Simulation)
      |                         |
      |                         +─> Layer 02 (Threat Detection synthetic training)
      |                         +─> Layer 05 (Navigation trajectory testing)
Layer 01 (LLM Core) ──> Layer 04 (OpFor + AAR narrative support)
```

---

## Adapter Pattern

All simulator backends implement a common interface:

- `GenericSimAdapter`:
  - `connect`, `disconnect`, `is_connected`, `health_check`
  - `start_simulation`, `pause_simulation`, `stop_simulation`, `reset_simulation`
  - `step`, `get_state`
  - `spawn_entity`, `remove_entity`, `set_entity_target`
  - `load_scenario`, `get_sim_time`

### Implemented adapters

- `BuiltinPhysicsEngine`
  - Always available, in-process fallback.
  - Supports entity movement, simple collision damage, and scenario loading.
  - Hard cap: 200 entities.
- `GazeboAdapter`
  - Uses ROS2 `rclpy` when available.
  - Gracefully reports unavailable if ROS2 is not installed.
- `AirSimAdapter`
  - Uses `airsim` package when installed.
  - Graceful fallback when unavailable.
- `JSBSimAdapter`
  - Uses `jsbsim` package for aircraft simulation.
  - Graceful fallback when unavailable.
- `PanopticonAdapter`
  - HTTP adapter using `urllib.request`.
  - No external SDK required.

---

## Built-in Physics Engine

The built-in engine provides tactical rehearsal capability without external simulators.

### Capabilities
- Spawns entities with force/allegiance metadata.
- Target-based straight-line kinematic movement.
- Collision detection (<= 5 meters).
- Damage model for enemy/friendly collisions.
- Emits event stream (`spawn`, `engagement_started`, `entity_killed`).

### Limitations
- No aerodynamics, gravity, or advanced terrain physics.
- Simplified engagement model.
- Intended for interface validation and rapid mission-loop testing.

---

## Wargaming System

### Scenario YAML format
Scenarios are loaded from `configs/scenarios/*.yaml` and parsed by `ScenarioEngine`.

Core fields:
- `name`, `type`, `description`
- `terrain`, `weather`
- `forces` (friendly/enemy)
- `objectives` with `success_condition`
- `rules_of_engagement`, `duration_seconds`, `parameters`

### OPFOR strategies

`OpForGenerator` supports:
- `static`: no movement commands
- `scripted`: deterministic waypoint behavior
- `random`: randomized maneuver within terrain bounds
- `adaptive`: LLM-assisted behavior with fallback to random

Adaptive mode:
- Queries LLM on cadence (default every N ticks).
- Caches response to reduce overhead.
- Falls back safely when parsing/engine unavailable.

### Scenario execution

`ScenarioRunner`:
1. Loads scenario into adapter.
2. Starts replay recording.
3. Steps simulation tick-by-tick.
4. Applies OPFOR behavior.
5. Evaluates objectives and termination criteria.
6. Stops replay and generates AAR.

### AAR generation

`AARGenerator` computes:
- Friendly/enemy losses
- Engagement count
- Outcome (`victory`, `defeat`, `draw`, `incomplete`)
- Lessons learned (LLM-assisted or statistics fallback)

---

## Replay System

`ReplayRecorder` stores runs as:
- JSONL state stream: `{replay_id}.jsonl`
- Metadata sidecar: `{replay_id}.meta.json`

Properties:
- Streaming write/read (no full-file memory load).
- 500MB max replay size guard.
- Artifact metadata includes duration, tick count, file size.

---

## Synthetic Data System

`SyntheticDataManager` orchestrates:
- `TabularGenerator`
  - Network traffic, sensor telemetry, logistics records
- `TrajectoryGenerator`
  - UAV flight, patrol, vehicle route, evasive trajectory, swarm trajectories
- `ScenarioDataGenerator`
  - Labeled tactical threat-event timelines
- `DatasetManifest`
  - Dataset metadata registration and checksum verification

Output paths:
- Data: `data/synthetic/`
- Manifest metadata: `data/manifests/`

---

## Backward Data Flow to Prior Layers

Layer 04 outputs are designed for upstream training pipelines:
- Threat events and synthetic scenarios feed Layer 02 detection/classification tests.
- Trajectory datasets feed navigation and autonomy stress tests.
- Replay artifacts support mission after-action learning loops.

---

## API Reference (Phase 7 Routes)

Base prefix: `/simulation`

### Adapters
- `GET /simulation/status`
- `GET /simulation/adapters`
- `POST /simulation/adapters/{name}/connect`
- `POST /simulation/adapters/{name}/disconnect`
- `GET /simulation/adapters/{name}/state`

### Scenarios
- `GET /simulation/scenarios`
- `POST /simulation/scenarios/load`
- `POST /simulation/scenarios/{id}/run`
- `POST /simulation/scenarios/{id}/stop`
- `GET /simulation/scenarios/{id}/status`
- `GET /simulation/scenarios/{id}/aar`

### Wargaming
- `POST /simulation/wargame/opfor/generate`
- `POST /simulation/wargame/forces/build`

### Synthetic Data
- `POST /simulation/synthetic/generate`
- `GET /simulation/synthetic/datasets`
- `GET /simulation/synthetic/datasets/{id}`
- `POST /simulation/synthetic/datasets/{id}/verify`

### Replays
- `GET /simulation/replays`
- `GET /simulation/replays/{id}`

---

## Configuration

Primary config:
- `configs/simulation.yaml`

Scenario configs:
- `configs/scenarios/urban_patrol.yaml`
- `configs/scenarios/convoy_ambush.yaml`
- `configs/scenarios/air_defense.yaml`
- `configs/scenarios/swarm_vs_swarm.yaml`

---

## Integration with Phases 1–6

- Imports from existing packages only:
  - `src.llm_core`
  - `src.threat_detection`
  - `src.sensor_fusion`
- No modifications required in prior phase modules (except API include in `server.py`).
- `SimulationState` conversion helpers produce:
  - Layer 02 `ThreatEvent` objects.
  - Layer 02 `SensorReading` objects.

---

## Testing Instructions

Run simulation test bundle (without external simulators):

```bash
python3 -m pytest tests/test_simulation_*.py tests/test_base_adapter.py tests/test_gazebo_adapter.py tests/test_jsbsim_adapter.py tests/test_panopticon_adapter.py tests/test_replay_*.py tests/test_scenario_*.py tests/test_opfor_*.py tests/test_aar_*.py tests/test_synthetic_*.py -v
```

External simulator packages are optional; adapter tests validate graceful unavailable behavior.

---

## Demo Scripts

- `python3 scripts/run_simulation_demo.py`
- `python3 scripts/demo_wargame.py`
- `python3 scripts/demo_synthetic_data.py`

---

## Future Work (Phase 8 Navigation Integration)

- Closed-loop coupling to navigation planner for trajectory correction.
- Richer terrain and obstacle models for route denial simulation.
- Adversarial EW/GNSS-denied navigation benchmarks.
- Hardware-in-the-loop timing profiles for mission certification.

