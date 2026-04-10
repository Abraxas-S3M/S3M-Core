# Automatic-Target-Recognition-using-SAR-Imagery integration

This wrapper provides a sovereign S3M sensor-fusion integration for **Automatic-Target-Recognition-using-SAR-Imagery**.

## Tactical role

Military/tactical context: SAR-based ATR preserves target-recognition capability under obscurants, darkness, or contested weather where EO feeds are unreliable.

## Adapter

- Class: `AutomaticTargetRecognitionUsingAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.automatic-target-recognition-using-sar-i`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
