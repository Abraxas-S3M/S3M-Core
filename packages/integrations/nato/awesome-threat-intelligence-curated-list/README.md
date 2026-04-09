# awesome-threat-intelligence (curated list) Integration

S3M NATO-domain wrapper for **awesome-threat-intelligence**.

## Military / Tactical Context
This adapter supports deterministic OSINT doctrine rehearsal by providing
structured threat-intelligence resource recommendations without internet
dependency, suitable for disconnected mission planning cells.

## Adapter Class
- `AwesomeThreatIntelligencecuratedAdapter`
- `integration_id = "awesome-threat-intelligence-curated-list"`
- `domain = "nato"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local prerequisites only.
- `execute()` returns deterministic fixture content in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
