# UAV-tracking-tank integration

This wrapper provides a sovereign S3M sensor-fusion integration for **UAV-tracking-tank**.

## Tactical role

Military/tactical context: Persistent UAV tracking of armored targets enables strike coordination and route denial with reduced sensor handoff latency.

## Adapter

- Class: `UavTrackingTankAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.uav-tracking-tank`

## Runtime behavior

- Airgapped mode always serves `fixtures/sample_response.json`.
- Online mode validates local runtime availability and returns readiness metadata.
- No external API calls are performed.
