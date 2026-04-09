# awesome-threat-intelligence (adapt) Integration

S3M military-domain wrapper for **awesome-threat-intelligence** adaptation.

## Military / Tactical Context
This adapter supports risk-forecasting workflows with deterministic OSINT
reference outputs for mission planning in airgapped command environments.

## Adapter Class
- `AwesomeThreatIntelligenceadaptAdapter`
- `integration_id = "awesome-threat-intelligence-adapt"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local command/module hints and local paths.
- `execute()` returns fixture-backed responses while airgapped.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
