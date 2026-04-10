# awesome-xmpp Integration

S3M communications-domain wrapper for **awesome-xmpp**.

## Military / Tactical Context
This adapter helps sovereign command elements assess and orchestrate secure
communications channels while operating in contested or disconnected theaters.

## Adapter Class
- `AwesomeXmppAdapter`
- `integration_id = "awesome-xmpp"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.awesome-xmpp`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
