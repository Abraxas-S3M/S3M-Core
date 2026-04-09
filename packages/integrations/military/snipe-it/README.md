# Snipe-IT Integration

S3M military-domain wrapper for **Snipe-IT**.

## Military / Tactical Context
This adapter helps logistics and procurement cells maintain accountability of
mission-essential equipment in sovereign, disconnected operating conditions.

## Adapter Class
- `SnipeItAdapter`
- `integration_id = "snipe-it"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
