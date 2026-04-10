# nav2 (ROS2 Navigation) Integration

S3M navigation-domain adapter for **nav2** (`https://github.com/ros-planning/navigation2`).

## Military / Tactical Context
This adapter enables offline validation of ROS2 navigation workflows for tactical route planning, obstacle-aware control, and resilient maneuver execution in denied-network environments.

## Adapter Class
- `Nav2ros2NavigationAdapter`
- `integration_id = "nav2-ros2-navigation"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.nav2-ros2-navigation`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local nav2 command/toolchain signals.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
