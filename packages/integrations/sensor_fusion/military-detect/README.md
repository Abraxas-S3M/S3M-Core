# Military-Detect integration

S3M sensor-fusion wrapper for **Military-Detect**.

## Military / Tactical Context
This adapter supports remote sensing target-detection workflows so ISR analysts can triage airbase, warship, missile, and bridge signatures during contested operations.

## Adapter
- Class: `MilitaryDetectAdapter`
- Inherits: `packages.integrations.base.IntegrationAdapter`
- Logger: `s3m.integrations.sensor_fusion.military-detect`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime binaries/paths only.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
`fixtures/sample_response.json`
