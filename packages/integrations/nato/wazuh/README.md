# Wazuh Integration

S3M NATO-domain wrapper for **Wazuh**.

## Military / Tactical Context
This adapter provides deterministic SOC rehearsal outputs so cyber defenders can
practice endpoint and network threat triage while operating in disconnected or
contested coalition environments.

## Adapter Class
- `WazuhAdapter`
- `integration_id = "wazuh"`
- `domain = "nato"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` verifies local Wazuh command/path readiness only.
- `execute()` returns fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
