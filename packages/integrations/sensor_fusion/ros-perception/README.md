# ros-perception Integration

S3M adapter for [ros-perception](https://github.com/ros-perception) in the `sensor_fusion` domain.

## Tactical purpose

This wrapper standardizes readiness checks for ROS perception components used by unmanned and autonomous mission platforms.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime presence (`ros2`/`rospack`) without external APIs
- Returns deterministic fixture data in airgapped mode

## Airgapped behavior

When running in airgapped mode, `execute()` returns `fixtures/sample_response.json` to emulate pipeline readiness outputs offline.
