# AircraftDetectionYolov5 integration

This wrapper provides a sovereign S3M sensor-fusion integration for **AircraftDetectionYolov5**.

## Tactical role

Military/tactical context: Aircraft detection integration feeds air-defense common operating pictures with rapid visual confirmation of hostile platforms.

## Adapter

- Class: `Aircraftdetectionyolov5Adapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.aircraftdetectionyolov5`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
