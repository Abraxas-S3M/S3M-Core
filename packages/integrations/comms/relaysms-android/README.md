# RelaySMS-Android Integration

S3M communications-domain wrapper for **RelaySMS-Android** secure SMS relay
operations in disconnected environments.

## Military / Tactical Context
This adapter supports command continuity by providing deterministic message relay
status snapshots when units are operating without internet transport.

## Adapter Class
- `RelaysmsAndroidAdapter`
- `integration_id = "relaysms-android"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.relaysms-android`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
