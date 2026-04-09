# osint-framework Integration

S3M wrapper for the [osint-framework](https://github.com/fr4nc1stein/osint-framework) repository.

## Military/Tactical Context

This adapter provides a standardized interface for intelligence teams to perform
OSINT resource discovery and prepare mission briefings in disconnected or
contested operating conditions.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: checks local command/module availability and returns a
  runtime handoff payload for orchestrator-controlled execution.

## Files

- `adapter.py`: `OsintFrameworkAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response

