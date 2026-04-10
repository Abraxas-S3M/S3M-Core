# Machine-Learning-Based-Intrusion-Detection-System integration

S3M sensor-fusion wrapper for **Machine-Learning-Based-Intrusion-Detection-System**.

## Military / Tactical Context
This adapter supports UAV swarm cyber defense by consolidating model-driven intrusion assessments that protect command and telemetry links during active operations.

## Adapter
- Class: `MachineLearningBasedIntrusionAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.machine-learning-based-intrusion-detecti`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` verifies local runtime tools only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
`fixtures/sample_response.json`
