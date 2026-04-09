# coreDSUnreal (samples) Integration

S3M wrapper for the [distributedsimulationtools/coreDSUnreal_Sample_AutomaticMode](https://github.com/distributedsimulationtools/coreDSUnreal_Sample_AutomaticMode) repository.

## Military/Tactical Context

This adapter supports distributed simulation interoperability by standardizing
DIS/Unreal sample workflows for mission rehearsal, entity-state synchronization,
and after-action playback on sovereign systems.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic DIS/Unreal fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local dependencies and returns a runtime handoff
  payload for deployment-specific execution.

## Files

- `adapter.py`: `CoredsunrealsamplesAdapter`
- `manifest.yaml`: integration metadata
- `fixtures/sample_response.json`: deterministic airgapped response
