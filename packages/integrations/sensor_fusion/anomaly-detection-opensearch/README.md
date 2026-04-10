# anomaly-detection (OpenSearch) integration

S3M sensor-fusion wrapper for **anomaly-detection (OpenSearch)**.

## Military / Tactical Context
This adapter supports anomaly monitoring of mission logs and metrics so operators can detect cyber or platform instability before it degrades battlefield systems.

## Adapter
- Class: `AnomalyDetectionopensearchAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.anomaly-detection-opensearch`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime prerequisites.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
`fixtures/sample_response.json`
