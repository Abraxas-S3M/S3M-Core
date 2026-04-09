# Suricata Integration

S3M NATO-domain wrapper for **Suricata**.

## Military / Tactical Context
This adapter supports blue-team network defense rehearsals for coalition-style
operations where analysts must validate IDS/IPS workflows on disconnected
infrastructure before deployment in contested environments.

## Adapter Class
- `SuricataAdapter`
- `integration_id = "suricata"`
- `domain = "nato"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks only local Suricata runtime readiness.
- `execute()` returns deterministic fixture data when airgapped.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
