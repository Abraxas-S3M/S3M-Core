# simplex-chat Integration

S3M comms-domain wrapper for **simplex-chat** secure messaging workflows.

## Military / Tactical Context
This adapter supports metadata-minimized message routing so tactical teams can
coordinate under interception pressure while preserving communication secrecy.

## Adapter Class
- `SimplexChatAdapter`
- `integration_id = "simplex-chat"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.simplex-chat`

## Behavior
- `get_manifest()` loads integration metadata from `manifest.yaml`.
- `validate_availability()` checks local binary or configured local path only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
