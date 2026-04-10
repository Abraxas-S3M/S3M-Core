# berty Integration

S3M comms-domain wrapper for **berty** secure peer-to-peer tactical messaging.

## Military / Tactical Context
This adapter supports squad-level communications continuity when centralized
infrastructure is unavailable, enabling resilient routing in contested terrain.

## Adapter Class
- `BertyAdapter`
- `integration_id = "berty"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.berty`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or operator-defined local paths.
- `execute()` returns deterministic fixture data while airgapped.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
