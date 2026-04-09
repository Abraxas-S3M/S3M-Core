# osint Integration

S3M wrapper for the [doctorfree/osint](https://github.com/doctorfree/osint) repository.

## Military/Tactical Context

This adapter helps intelligence operators filter and stage curated OSINT tools
for mission-focused collection workflows in sovereign, airgapped environments.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local command/module availability and returns a
  runtime handoff payload for orchestrator-controlled execution.

## Files

- `adapter.py`: `OsintAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response

