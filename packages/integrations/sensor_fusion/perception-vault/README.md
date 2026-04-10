# perception_vault Integration

S3M sensor-fusion adapter for **perception_vault** (`https://github.com/peakyquest/perception_vault`).

## Military / Tactical Context
This adapter validates offline ROS2 perception-fusion pipeline readiness so commanders can maintain contact tracking and route awareness during communications denial and intermittent sensor degradation.

## Adapter Class
- `PerceptionVaultAdapter`
- `integration_id = "perception-vault"`
- `domain = "sensor_fusion"`
- Logger: `s3m.integrations.sensor_fusion.perception-vault`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local ROS2 runtime hints.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
