# Malcolm Integration

S3M military-domain wrapper for **Malcolm**.

## Military / Tactical Context
This adapter supports threat hunting on mission networks where command-post
cyber teams must detect hostile traffic without cloud dependency.

## Adapter Class
- `MalcolmAdapter`
- `integration_id = "malcolm"`
- `domain = "military"`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured paths.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
