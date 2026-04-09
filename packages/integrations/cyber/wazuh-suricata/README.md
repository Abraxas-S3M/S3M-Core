# wazuh-suricata Integration

S3M cyber-domain wrapper for **wazuh-suricata**.

## Military / Tactical Context
This adapter helps cyber defense cells maintain mission assurance by providing a
standard interface for alert triage, response orchestration, and offline fallback
behavior in airgapped deployments.

## Adapter Class
- `WazuhSuricataAdapter`
- `integration_id = "wazuh-suricata"`
- `domain = "cyber"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries/config/env hints only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
