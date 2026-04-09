# LIO_SAM_6AXIS Integration

S3M adapter for [LIO_SAM_6AXIS](https://github.com/JokerJohn/LIO_SAM_6AXIS) in the `navigation` domain.

## Tactical purpose

This wrapper supports secure readiness checks for 6-axis LiDAR-inertial odometry stacks in GNSS-denied tactical deployments.

## Capabilities

- Loads wrapper metadata from `manifest.yaml`
- Validates local binary and ROS package presence
- Uses fixture outputs in airgapped mode for deterministic integration tests

## Airgapped behavior

In airgapped mode, `execute()` returns `fixtures/sample_response.json` and avoids live tool invocation.
