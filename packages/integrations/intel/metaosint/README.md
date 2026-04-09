# MetaOSINT Integration

S3M wrapper for [MetaOSINT](https://github.com/MetaOSINT) resources.

## Military/Tactical Context

This adapter supports mission planning teams by identifying relevant public
OSINT resources for constrained collection windows and disconnected operations.

## Behavior

- **Airgapped mode** (`mode="airgapped"` or `S3M_AIRGAPPED=true`): returns
  deterministic fixture data from `fixtures/sample_response.json`.
- **Online mode**: validates local command/module availability and returns a
  runtime handoff payload for orchestrator-controlled execution.

## Files

- `adapter.py`: `MetaosintAdapter`
- `manifest.yaml`: discovery metadata
- `fixtures/sample_response.json`: airgapped sample response

