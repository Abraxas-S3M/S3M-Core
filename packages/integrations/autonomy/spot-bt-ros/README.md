# spot_bt_ros Integration

S3M adapter for `spot_bt_ros`, a ROS2 behavior-tree package for Boston
Dynamics Spot platforms.

## Tactical purpose

This integration helps S3M planners assess whether local Spot mission behavior
trees are runnable for reconnaissance, perimeter patrol, and route clearance.

## Files

- `adapter.py` - `SpotBtRosAdapter` implementation.
- `manifest.yaml` - metadata for integration discovery.
- `fixtures/sample_response.json` - deterministic airgapped response.

## Airgapped behavior

In airgapped mode, `execute()` returns fixture data so edge simulations produce
stable outputs without external dependencies.

## Online behavior

`validate_availability()` checks local ROS2 tool visibility and confirms
`spot_bt_ros` package discovery via `ros2 pkg prefix`.
