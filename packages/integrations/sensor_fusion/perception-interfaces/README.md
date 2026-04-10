# perception_interfaces Integration

S3M adapter for [perception_interfaces](https://github.com/ika-rwth-aachen/perception_interfaces) in the `sensor_fusion` domain.

## Tactical purpose

This wrapper standardizes checks for common ROS/ROS2 perception interfaces used by autonomous mission stacks.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime presence (`ros2`/`rospack`) without external APIs
- Returns deterministic fixture data in airgapped mode

## Airgapped behavior

When running in airgapped mode, `execute()` returns `fixtures/sample_response.json` so interface validation workflows can be exercised offline.
