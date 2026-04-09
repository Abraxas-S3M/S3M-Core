# py_trees_ros Integration

S3M autonomy wrapper for [`py_trees_ros`](https://github.com/splintered-reality/py_trees_ros).

## Tactical Purpose

Bridges behavior-tree autonomy logic with ROS execution channels used by mission robotics and unmanned systems.

## Airgapped Operation

- `mode="airgapped"` emits deterministic fixture output from `fixtures/sample_response.json`.
- No network dependency is required.

## Adapter Class

- `PyTreesRosAdapter`
- `integration_id = "py-trees-ros"`
- `domain = "autonomy"`
