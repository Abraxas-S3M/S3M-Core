# SignalRange Integration

S3M military-domain wrapper for **SignalRange**.

## Military / Tactical Context
This adapter supports electronic warfare training by returning deterministic
ground-station simulation outputs in disconnected command environments.

## Adapter Class
- `SignalrangeAdapter`
- `integration_id = "signalrange"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks only local binaries and configured local paths.
- `execute()` provides fixture-backed responses when airgapped.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
