# military-yolov5 integration

This wrapper provides a sovereign S3M sensor-fusion integration for **military-yolov5**.

## Tactical role

Military/tactical context: Video-based object detection supports convoy overwatch and perimeter defense by continuously identifying hostile assets and weapons.

## Adapter

- Class: `MilitaryYolov5Adapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.military-yolov5`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
