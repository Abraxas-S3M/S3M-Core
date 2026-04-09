# vlms_with_ros2_workshop Integration (HMI Domain)

S3M wrapper for [vlms_with_ros2_workshop](https://github.com/nilutpolkashyap/vlms_with_ros2_workshop).

## Tactical purpose

This adapter helps Human-Machine Teaming operators rehearse ROS2 Vision-Language Model perception flows in disconnected environments before mission deployment.

## Adapter class

- `VlmsWithRos2WorkshopAdapter`
- `integration_id = "vlms-with-ros2-workshop"`
- `domain = "hmi"`
- logger: `s3m.integrations.hmi.vlms-with-ros2-workshop`

## Airgapped behavior

When `mode="airgapped"`, `execute()` returns deterministic fixture data from `fixtures/sample_response.json` for offline validation.
