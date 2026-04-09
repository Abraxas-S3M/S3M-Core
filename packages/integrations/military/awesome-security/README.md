# awesome-security Integration

S3M military-domain wrapper for **awesome-security**.

## Military / Tactical Context
This adapter supports cyber readiness checks by mapping curated defensive tools
to mission-network validation workflows in airgapped command environments.

## Adapter Class
- `AwesomeSecurityAdapter`
- `integration_id = "awesome-security"`
- `domain = "military"`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks for local detection/security tool presence.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
