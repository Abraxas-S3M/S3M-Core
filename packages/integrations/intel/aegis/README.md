# AEGIS Integration

S3M wrapper for the [AEGIS](https://github.com/alex-armand-blumberg/AEGIS) repository.

## Military/Tactical Context

This adapter packages early-warning and geostrategic intelligence outputs into a
uniform S3M interface so command teams can maintain decision tempo in
airgapped operational environments.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local command/module availability and returns a
  runtime handoff payload for orchestrator-controlled execution.

## Files

- `adapter.py`: `AegisAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response

