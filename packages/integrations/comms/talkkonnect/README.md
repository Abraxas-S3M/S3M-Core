# talkkonnect Integration

S3M communications-domain wrapper for **talkkonnect**, a headless Mumble
push-to-talk client suited for tactical voice-network workflows.

## Military / Tactical Context
This adapter supports unit-level voice coordination by providing deterministic
readiness snapshots for encrypted, radio-style communication paths in
disconnected deployments.

## Adapter Class
- `TalkkonnectAdapter`
- `integration_id = "talkkonnect"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.talkkonnect`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
