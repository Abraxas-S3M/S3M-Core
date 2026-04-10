# AI-Driven-Threat-Detection-System Integration

S3M adapter for [AI-Driven-Threat-Detection-System](https://github.com/melisa48/AI-Driven-Threat-Detection-System) in the `sensor_fusion` domain.

## Tactical purpose

This wrapper supports tactical SOC teams by normalizing anomaly outputs from local network telemetry in disconnected operations.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime presence (Python + ML stack) without external APIs
- Returns deterministic fixture data in airgapped mode

## Airgapped behavior

When running in airgapped mode, `execute()` returns `fixtures/sample_response.json` so cyber-defense drills remain reproducible.
