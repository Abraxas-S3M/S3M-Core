# OpenVAS Integration

S3M military-domain wrapper for **OpenVAS**.

## Military / Tactical Context
This adapter supports edge-device vulnerability assessments so mission cyber
teams can prioritize hardening actions for forward-deployed infrastructure.

## Adapter Class
- `OpenvasAdapter`
- `integration_id = "openvas"`
- `domain = "military"`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks for local scanner tooling and paths.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
