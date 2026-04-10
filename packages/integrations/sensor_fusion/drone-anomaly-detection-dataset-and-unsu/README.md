# Drone-Anomaly-Detection-Dataset-and-Unsupervised-Machine-Learning Integration

S3M adapter for [Drone-Anomaly-Detection-Dataset-and-Unsupervised-Machine-Learning](https://github.com/isot-lab/Drone-Anomaly-Detection-Dataset-and-Unsupervised-Machine-Learning) in the `sensor_fusion` domain.

## Tactical purpose

This wrapper supports defensive counter-UAS operations by standardizing Wi-Fi anomaly scoring outputs for offline mission systems.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime presence (Python/ML stack) without external APIs
- Returns deterministic fixture data in airgapped mode

## Airgapped behavior

When running in airgapped mode, `execute()` returns `fixtures/sample_response.json` so operator workflows can be tested without network access.
