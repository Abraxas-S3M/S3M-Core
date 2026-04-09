# military-sim-old Integration

S3M military-domain wrapper for **military-sim-old**.

## Military / Tactical Context
This adapter provides deterministic scenario outputs for command-post drills and
decision rehearsal when operational networks are disconnected or denied.

## Adapter Class
- `MilitarySimOldAdapter`
- `integration_id = "military-sim-old"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime availability only.
- `execute()` returns fixture-backed outputs in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
