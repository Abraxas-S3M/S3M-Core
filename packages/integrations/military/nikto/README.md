# Nikto Integration

S3M military-domain wrapper for **Nikto**.

## Military / Tactical Context
This adapter supports defensive vulnerability reconnaissance of mission web
assets so cyber operators can validate hardening baselines in disconnected
operations.

## Adapter Class
- `NiktoAdapter`
- `integration_id = "nikto"`
- `domain = "military"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local Nikto binaries and configured paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
