# S3M Phase 6 - Autonomy and Swarm (Layer 03)

## 1) Architecture Overview

Phase 6 introduces Layer 03, enabling autonomous tactical action after threat detection and LLM assessment.

```text
Layer 02 (Threat Detection) -> Layer 01 (LLM Core) -> Layer 03 (Autonomy) -> Layer 05 (Navigation)
                                                              \-> Layer 04 (Simulation)

Layer 03 Subsystems:
  - RL: Policy learning and runtime inference
  - Behavior Trees: OODA mission execution engine
  - Swarm: Multi-agent coordination and C2 protocol
  - XAI: Decision logs, explanations, and assurance checks
```

### Core Tactical Data Flow
1. Threat observations are assessed by Layer 01 engines.
2. Autonomy receives mission context + assessed risks.
3. Behavior trees and/or RL policies produce commands.
4. Swarm coordinator allocates tasks and issues validated commands.
5. Every decision is logged for command accountability and legal audit.

---

## 2) RL Subsystem

### Components
- `src/autonomy/rl/environments.py`
  - `MilitaryEnvironment`: single-agent contested terrain environment.
  - `DroneSwarmEnv`: multi-agent swarm environment with cohesion rewards.
- `src/autonomy/rl/reward_functions.py`
  - Composable tactical reward utilities.
- `src/autonomy/rl/policy_registry.py`
  - Local policy persistence: `models/policies/<name>/policy.pkl` + `metadata.json`.
- `src/autonomy/rl/agent_manager.py`
  - Backend selection: RLlib -> SB3 -> built-in deterministic fallback.

### Backend Fallback Strategy
Autonomy remains operational offline even if optional packages are absent.
- Preferred: Ray RLlib
- Secondary: Stable-Baselines3
- Fallback: `[BUILTIN] Rule-based fallback`

### Training Pipeline
1. Create environment (`MilitaryEnvironment` by default).
2. Create agent via `RLAgentManager.create_agent(...)`.
3. Train via `train(agent_id, n_steps=...)`.
4. Evaluate via `evaluate(...)`.
5. Persist via `save(...)`.

---

## 3) Behavior Tree Subsystem

### Components
- `src/autonomy/behavior_trees/nodes.py`
  - Core nodes: `SequenceNode`, `SelectorNode`, `ConditionNode`, `ActionNode`, `RepeatNode`, `InverterNode`
  - Tactical nodes: `PatrolNode`, `EngageNode`, `ReconNode`, `RetreatNode`, `HoldNode`, `RTBNode`
- `src/autonomy/behavior_trees/llm_replan_node.py`
  - `LLMReplanNode`: consults Layer 01 orchestrator when static logic is insufficient.
- `src/autonomy/behavior_trees/mission_tree.py`
  - Builds validated trees from YAML mission definitions.
- `src/autonomy/behavior_trees/mission_executor.py`
  - Thread-safe tick executor with mission status and audit tracking.

### YAML Mission Format
Mission YAMLs live in `configs/missions/`.

```yaml
mission:
  type: patrol
  tree:
    type: selector
    children:
      - type: sequence
        children:
          - type: condition
            check: "battery_pct < 15"
          - type: action
            node: "rtb"
      - type: action
        node: "patrol"
```

### LLM Replanning
- Prompt includes mission status, threats, and failed behavior.
- Parses action keywords: `ENGAGE`, `RETREAT`, `HOLD`, `REROUTE`, `ESCALATE`.
- On orchestrator failure, returns controlled `FAILURE` and records fallback reason.

---

## 4) Swarm Subsystem

### Components
- `src/autonomy/swarm/coordinator.py` - central control plane.
- `src/autonomy/swarm/formations.py` - formation geometry + transition scoring.
- `src/autonomy/swarm/task_allocator.py` - capability-aware mission role assignment.
- `src/autonomy/swarm/swarm_protocol.py` - command creation/validation/serialization.
- `src/autonomy/swarm/nl_commander.py` - English/Arabic NL -> `SwarmCommand`.

### Formation Types
- LINE, WEDGE, DIAMOND, CIRCLE
- ECHELON_LEFT, ECHELON_RIGHT
- COLUMN, SPREAD, CUSTOM

### Task Allocation Logic
1. Filter by required capability and availability.
2. Score by proximity, battery, and sensor match.
3. Assign leader/scout/followers.
4. Flag understaffed mission in mission parameters.

### NL Command Parsing
- LLM-assisted parsing first (optional).
- Deterministic fallback keywords:
  - English: move/hold/engage/RTB/emergency stop/formation commands.
  - Arabic: `توقف`, `هجوم`, `انسحاب`, `دورية`, `عودة للقاعدة`.

---

## 5) XAI Subsystem

### Components
- `src/autonomy/xai/decision_log.py`
  - FIFO decision archive with filtering, stats, and export.
- `src/autonomy/xai/decision_explainer.py`
  - Structured + operator-friendly explanations.
  - Optional Captum feature attribution if installed.
- `src/autonomy/xai/assurance_checker.py`
  - Enforces risk/confidence/ROE review policy.

### Assurance Policy Highlights
- High-risk or low-confidence decisions are review-flagged.
- ENGAGE under `weapons_hold` is blocked.
- STRIKE decisions always require human review.
- LLM uncertainty can trigger review flags.

---

## 6) API Endpoints (Phase 6)

Mounted via `src/api/autonomy_routes.py` in `src/api/server.py`.

### Agents
- `GET /autonomy/status`
- `GET /autonomy/agents`
- `GET /autonomy/agents/{agent_id}`
- `POST /autonomy/agents/register`
- `PATCH /autonomy/agents/{agent_id}`
- `DELETE /autonomy/agents/{agent_id}`

### Missions
- `POST /autonomy/mission/start`
- `POST /autonomy/mission/{mission_id}/abort`
- `GET /autonomy/mission/{mission_id}`
- `GET /autonomy/missions`

### Swarm
- `POST /autonomy/swarm/command`
- `POST /autonomy/swarm/command/nl`
- `GET /autonomy/swarm/formation`
- `POST /autonomy/swarm/formation`
- `POST /autonomy/swarm/emergency-stop`
- `GET /autonomy/swarm/status`

### RL
- `POST /autonomy/rl/train`
- `GET /autonomy/rl/policies`
- `POST /autonomy/rl/policies/{name}/load`

### XAI / Decisions
- `GET /autonomy/decisions`
- `GET /autonomy/decisions/{decision_id}`
- `GET /autonomy/decisions/{decision_id}/explain`
- `GET /autonomy/decisions/review-queue`
- `POST /autonomy/decisions/{decision_id}/approve`
- `POST /autonomy/decisions/{decision_id}/reject`

### Example: Register Agent
```json
POST /autonomy/agents/register
{
  "agent_id": "drone-1",
  "role": "leader",
  "state": "idle",
  "capability": "air",
  "position": [0, 0, 50],
  "heading": 0,
  "speed": 0,
  "battery_pct": 95,
  "fuel_pct": 100
}
```

---

## 7) Configuration Reference

### `configs/autonomy.yaml`
- RL backend defaults and training settings.
- Behavior tree tick configuration.
- Swarm limits and command TTL.
- XAI thresholds.

### Mission Profiles
- `configs/missions/patrol.yaml`
- `configs/missions/recon.yaml`
- `configs/missions/intercept.yaml`

---

## 8) Integration with Phases 1–5

- Imports Layer 01 via `src.llm_core` for replan/NL parsing.
- Consumes threat context and mission inputs from upstream layers.
- Outputs actionable command objects for downstream navigation/simulation.
- Does not modify Phase 1–5 packages.

---

## 9) Testing Instructions

Run autonomy test suite:

```bash
python -m pytest \
  tests/test_autonomy_*.py \
  tests/test_rl_*.py \
  tests/test_behavior_*.py \
  tests/test_swarm_*.py \
  tests/test_task_*.py \
  tests/test_nl_*.py \
  tests/test_decision_*.py \
  tests/test_assurance_*.py \
  -v
```

Run API and demos:

```bash
python scripts/start_api.py
python scripts/run_autonomy_demo.py
python scripts/demo_behavior_tree.py
python scripts/demo_swarm.py
```

---

## 10) Future Work (Phase 7 Simulation Integration)

- Closed-loop autonomy-in-simulation evaluation harness.
- High-fidelity vehicle and sensor plugins.
- Multi-swarm conflict deconfliction and contested comms modeling.
- Formal policy verification for mission-critical engagement rules.
