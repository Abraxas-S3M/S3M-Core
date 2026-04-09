# ORB_SLAM3 Integration (Military Domain)

S3M wrapper for [ORB_SLAM3](https://github.com/UZ-SLAMLab/ORB_SLAM3).

## Tactical purpose

This adapter supports visual/stereo/inertial localization readiness checks so
UAV teams can preserve navigation continuity in GPS-denied theaters.

## Adapter class

- `OrbSlam3Adapter`
- `integration_id = "orb-slam3"`
- `domain = "military"`
- logger: `s3m.integrations.military.orb-slam3`

## Airgapped behavior

When `mode="airgapped"` (or `S3M_AIRGAPPED=true`), `execute()` returns
`fixtures/sample_response.json` and does not call external services.
