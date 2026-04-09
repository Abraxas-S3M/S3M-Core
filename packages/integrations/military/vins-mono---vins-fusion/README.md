# VINS-Mono / VINS-Fusion Integration (Military Domain)

S3M wrapper for [VINS-Mono](https://github.com/HKUST-Aerial-Robotics/VINS-Mono).

## Tactical purpose

This adapter supports visual-inertial odometry readiness checks for UAV missions
that require robust pose estimation in contested and disconnected environments.

## Adapter class

- `VinsMonoVinsAdapter`
- `integration_id = "vins-mono---vins-fusion"`
- `domain = "military"`
- logger: `s3m.integrations.military.vins-mono---vins-fusion`

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns
`fixtures/sample_response.json` and does not call external services.
