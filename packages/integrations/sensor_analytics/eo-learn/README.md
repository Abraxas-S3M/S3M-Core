# eo-learn Integration

S3M sensor-analytics adapter for **eo-learn** (`https://github.com/sentinel-hub/eo-learn`).

## Military / Tactical Context
This wrapper supports EO-driven battlespace monitoring by validating local
pipeline readiness and enabling deterministic fixture responses in airgapped
operations.

## Adapter Class
- `EoLearnAdapter`
- `integration_id = "eo-learn"`
- `domain = "sensor_analytics"`
- Logger: `s3m.integrations.sensor_analytics.eo-learn`

## Behavior
- `get_manifest()` reads metadata from `manifest.yaml`.
- `validate_availability()` checks local module/binary readiness.
- `execute()` returns fixture-backed output in airgapped mode.

## Airgapped Fixture
Fixture path: `fixtures/sample_response.json`
