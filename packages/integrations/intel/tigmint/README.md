# TIGMINT Integration

S3M wrapper for the [TIGMINT](https://github.com/TIGMINT/TIGMINT) repository.

## Military/Tactical Context

This adapter standardizes social-media OSINT collection outputs so tactical
intelligence teams can rapidly assemble mission briefings in sovereign
environments.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local command/module availability and returns a
  runtime handoff payload for orchestrator-controlled execution.

## Files

- `adapter.py`: `TigmintAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response

