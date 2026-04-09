# air-c2-cop-python Integration

S3M wrapper for the [Esri/air-c2-cop-python](https://github.com/Esri/air-c2-cop-python) repository.

## Military/Tactical Context

This adapter supports air operations command-and-control rehearsals by exposing a
controlled interface for Common Operating Picture generation, airspace overlays,
and tasking deconfliction in sovereign environments.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic COP fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local dependencies and returns a runtime handoff
  payload for platform-specific execution.

## Files

- `adapter.py`: `AirC2CopPythonAdapter`
- `manifest.yaml`: integration metadata
- `fixtures/sample_response.json`: deterministic airgapped response
