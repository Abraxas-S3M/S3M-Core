# UAVSwarm-dataset integration

S3M sensor-fusion wrapper for **UAVSwarm-dataset**.

## Military / Tactical Context
This adapter helps mission AI teams curate and validate annotated swarm imagery for robust target-detection and tracking models on offline command infrastructure.

## Adapter
- Class: `UavswarmDatasetAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.uavswarm-dataset`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local dataset/runtime presence.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
`fixtures/sample_response.json`
