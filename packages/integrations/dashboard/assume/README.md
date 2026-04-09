# Assume Integration

S3M wrapper for the [Assume](https://github.com/assume-framework/assume) dashboard repository.

## Military/Tactical Context

This adapter supports mission rehearsal and staff training by exposing an
agent-based simulation dashboard through the standardized `IntegrationAdapter`
contract used by the S3M orchestration layer.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  `fixtures/sample_response.json` for offline training runs.
- **Online mode**: validates local toolchain presence before returning a
  runtime handoff payload for orchestrator-controlled execution.

## Files

- `adapter.py`: `AssumeAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: offline fixture payload

