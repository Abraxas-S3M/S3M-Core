# tfc (Tinfoil Chat) Integration

S3M comms-domain wrapper for **tfc (Tinfoil Chat)** secure messaging workflows.

## Military / Tactical Context
This adapter supports endpoint-secure and onion-routed communications for
high-risk missions requiring strict traffic-flow control and compartmentation.

## Adapter Class
- `TfctinfoilChatAdapter`
- `integration_id = "tfc-tinfoil-chat"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.tfc-tinfoil-chat`

## Behavior
- `get_manifest()` loads integration metadata from `manifest.yaml`.
- `validate_availability()` checks local binary or configured local path only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
