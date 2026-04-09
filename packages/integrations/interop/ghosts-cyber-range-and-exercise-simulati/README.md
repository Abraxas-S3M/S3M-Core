# ghosts-cyber-range-and-exercise-simulation-tools Integration

S3M wrapper for the [cmu-sei/ghosts-cyber-range-and-exercise-simulation-tools](https://github.com/cmu-sei/ghosts-cyber-range-and-exercise-simulation-tools) repository.

## Military/Tactical Context

This adapter standardizes cyber-range exercise interactions so joint operators
can rehearse defensive and adversary-emulation scenarios on sovereign
infrastructure without external service dependencies.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic range-state fixtures from `fixtures/sample_response.json`.
- **Online mode**: validates local tool/runtime availability and returns a
  runtime handoff payload for deployment-specific execution.

## Files

- `adapter.py`: `GhostsCyberRangeAndAdapter`
- `manifest.yaml`: integration metadata
- `fixtures/sample_response.json`: deterministic airgapped response
