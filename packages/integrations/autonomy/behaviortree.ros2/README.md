# BehaviorTree.ROS2 Integration

S3M autonomy wrapper for [`BehaviorTree.ROS2`](https://github.com/BehaviorTree/BehaviorTree.ROS2).

## Tactical Purpose

Integrates ROS2 behavior-tree plugins into a stable S3M adapter contract for autonomy nodes operating in mission-critical environments.

## Airgapped Operation

- `mode="airgapped"` serves fixture data from `fixtures/sample_response.json`.
- Adapter logic performs no remote API requests.

## Adapter Class

- `Behaviortreeros2Adapter`
- `integration_id = "behaviortree.ros2"`
- `domain = "autonomy"`
