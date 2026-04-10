# MultiRobot_Search_and_Rescue Integration

## Purpose

This adapter wraps `multirobot-search-and-rescue` for S3M swarm mission orchestration with deterministic,
airgapped execution paths.

Military/tactical context: command teams can validate multi-agent coordination
behaviors on isolated sovereign infrastructure before deployment in contested
communications environments.

## Adapter Class

- `MultirobotSearchAndRescueAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.swarm.multirobot-search-and-rescue`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local ROS2/runtime availability only (no external API calls)

## Manifest

Metadata is maintained in `manifest.yaml` and exposed via `get_manifest()`.
