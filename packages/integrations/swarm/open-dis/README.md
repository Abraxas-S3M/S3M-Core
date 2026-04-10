# open-dis Integration

S3M swarm-domain adapter for **open-dis** (`https://github.com/open-dis`).

## Military / Tactical Context
This adapter enables deterministic validation of DIS protocol workflows used by
distributed simulation federations for tactical entity-state exchange.

## Adapter Class
- `OpenDisAdapter`
- `integration_id = "open-dis"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.open-dis`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local DIS toolchain hints.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
