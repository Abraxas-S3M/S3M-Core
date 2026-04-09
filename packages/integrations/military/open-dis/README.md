# Open-DIS Integration

S3M military-domain wrapper for **Open-DIS**.

## Military / Tactical Context
This adapter supports distributed simulation exercises where mission systems
must exchange DIS protocol data reliably in denied or disconnected environments.

## Adapter Class
- `OpenDisAdapter`
- `integration_id = "open-dis"`
- `domain = "military"`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local module and command availability.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
