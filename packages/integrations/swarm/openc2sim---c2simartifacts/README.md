# OpenC2SIM / C2SIMArtifacts Integration

S3M swarm-domain adapter for **OpenC2SIM** (`https://github.com/OpenC2SIM`).

## Military / Tactical Context
This adapter delivers deterministic wrapper behavior for C2SIM artifact
validation used in command-and-simulation interoperability rehearsals.

## Adapter Class
- `Openc2simC2simartifactsAdapter`
- `integration_id = "openc2sim---c2simartifacts"`
- `domain = "swarm"`
- Logger: `s3m.integrations.swarm.openc2sim---c2simartifacts`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local C2SIM runtime/toolchain hints.
- `execute()` returns fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
