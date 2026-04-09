# Snort Integration

S3M military-domain wrapper for **Snort**.

## Military / Tactical Context
This adapter supports intrusion detection and anomaly triage on mission network
segments so defenders can train and validate response workflows offline.

## Adapter Class
- `SnortAdapter`
- `integration_id = "snort"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local Snort binaries and configured paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
