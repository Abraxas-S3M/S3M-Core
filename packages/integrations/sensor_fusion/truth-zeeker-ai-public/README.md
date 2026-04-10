# Truth-Zeeker-AI-Public Integration

S3M adapter for [Truth-Zeeker-AI-Public](https://github.com/dr-rakshith-truth-zeeker/Truth-Zeeker-AI-Public) in the `sensor_fusion` domain.

## Tactical purpose

This wrapper standardizes Zeek-log anomaly outputs for cyber-intelligence teams operating in disconnected and contested environments.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime presence (Zeek/Python stack) without external APIs
- Returns deterministic fixture data in airgapped mode

## Airgapped behavior

When running in airgapped mode, `execute()` returns `fixtures/sample_response.json` so detection playbooks can be validated offline.
