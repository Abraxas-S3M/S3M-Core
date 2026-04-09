# LIO-SAM Integration

S3M adapter for [LIO-SAM](https://github.com/TixiaoShan/LIO-SAM) in the `navigation` domain.

## Tactical purpose

This wrapper standardizes LiDAR-inertial odometry checks so navigation services can be rehearsed on sovereign, airgapped mission nodes.

## Capabilities

- Loads integration metadata from `manifest.yaml`
- Validates local runtime/tool availability (ROS package or binary presence)
- Returns deterministic fixture data in airgapped mode

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns `fixtures/sample_response.json` for offline mission rehearsal.
