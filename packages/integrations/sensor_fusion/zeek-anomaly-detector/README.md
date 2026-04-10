# zeek_anomaly_detector integration

S3M sensor-fusion wrapper for **zeek_anomaly_detector**.

## Military / Tactical Context
This adapter supports tactical cyber defense by scoring anomalous Zeek flow telemetry from mission networks, helping SOC analysts identify hostile activity quickly.

## Adapter
- Class: `ZeekAnomalyDetectorAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.zeek-anomaly-detector`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries and configured paths only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
`fixtures/sample_response.json`
