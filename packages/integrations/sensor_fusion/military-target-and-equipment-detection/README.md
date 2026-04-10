# Military-Target-and-Equipment-Detection integration

This wrapper provides a sovereign S3M sensor-fusion integration for **Military-Target-and-Equipment-Detection**.

## Tactical role

Military/tactical context: Forward observers can rapidly classify hostile personnel and equipment to prioritize fire-control and ISR resources during fast-moving engagements.

## Adapter

- Class: `MilitaryTargetAndEquipmentAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.military-target-and-equipment-detection`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
