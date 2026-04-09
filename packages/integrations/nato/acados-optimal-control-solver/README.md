# ACADOS (optimal control solver) Integration

S3M wrapper for [ACADOS](https://github.com/acados/acados).

## Military/Tactical Context

This adapter supports constrained trajectory optimization and model-predictive
control rehearsal for swarm and ISR maneuvers in disconnected or contested
operational environments.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local ACADOS module or command availability and
  returns a runtime handoff payload for orchestrator-managed execution.

## Files

- `adapter.py`: `AcadosoptimalControlSolverAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response
