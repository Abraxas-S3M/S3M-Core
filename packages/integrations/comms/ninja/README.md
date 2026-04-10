# Ninja Integration

S3M communications-domain wrapper for **Ninja**, a stealth-focused encrypted
command-and-control (C2) stack used for contested tactical environments.

## Military / Tactical Context
This adapter enables secure command routing checks for mission cells operating
in disconnected or bandwidth-constrained theaters where deterministic offline
behavior is required for rehearsal and fallback planning.

## Adapter Class
- `NinjaAdapter`
- `integration_id = "ninja"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.ninja`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and optional configured paths.
- `execute()` returns deterministic fixture output when airgapped.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
