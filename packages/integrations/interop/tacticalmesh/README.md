# TacticalMesh Integration

S3M wrapper for the [TamTunnel/TacticalMesh](https://github.com/TamTunnel/TacticalMesh) repository.

## Military/Tactical Context

This adapter supports coalition C2 networking rehearsals by standardizing mesh
topology and link-resilience workflows on sovereign infrastructure.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic mesh-state fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local TacticalMesh runtime availability and returns
  a runtime handoff payload for deployment-specific execution.

## Files

- `adapter.py`: `TacticalmeshAdapter`
- `manifest.yaml`: integration metadata
- `fixtures/sample_response.json`: deterministic airgapped response
