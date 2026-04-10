# ejabberd Integration

S3M communications-domain wrapper for **ejabberd** secure XMPP operations.

## Military / Tactical Context
This adapter supports sovereign command-and-control messaging by exposing
deterministic XMPP federation and encryption telemetry for disconnected and
contested battlespace networks.

## Adapter Class
- `EjabberdAdapter`
- `integration_id = "ejabberd"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.ejabberd`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
