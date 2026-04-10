# Covert-C2 Integration

S3M communications-domain wrapper for **Covert-C2** Native Messaging command routing.

## Military / Tactical Context
This adapter supports covert command relay paths between approved operator
endpoints, enabling low-signature message transport for contested-spectrum
operations in sovereign and disconnected environments.

## Adapter Class
- `CovertC2Adapter`
- `integration_id = "covert-c2"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.covert-c2`

## Behavior
- `get_manifest()` loads adapter metadata from `manifest.yaml`.
- `validate_availability()` checks only local binaries and configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
