# meshtastic Integration

S3M comms-domain wrapper for **meshtastic** secure mesh radio workflows.

## Military / Tactical Context
This adapter supports off-grid command messaging over low-power long-range mesh
links when infrastructure or satellite relays are contested.

## Adapter Class
- `MeshtasticAdapter`
- `integration_id = "meshtastic"`
- `domain = "comms"`
- Logger: `s3m.integrations.comms.meshtastic`

## Behavior
- `get_manifest()` loads integration metadata from `manifest.yaml`.
- `validate_availability()` checks local binary or configured local path only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
