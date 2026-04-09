# nav2_behavior_tree Integration

S3M adapter for the ROS2 Navigation2 `nav2_behavior_tree` package.

## Tactical purpose

This wrapper lets S3M autonomy planners verify behavior tree execution status for
route, obstacle, and replanning flows on edge nodes deployed in denied networks.

## Files

- `adapter.py` - `Nav2BehaviorTreeAdapter` implementation.
- `manifest.yaml` - integration metadata for discovery and registry.
- `fixtures/sample_response.json` - deterministic airgapped output.

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns
`fixtures/sample_response.json` so local mission simulations remain deterministic.

## Online behavior

`validate_availability()` checks whether `ros2` is installed and whether the
`nav2_behavior_tree` package is visible via `ros2 pkg prefix`.
