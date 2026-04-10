# VisionUAV-Navigation Integration

S3M navigation-domain adapter for **VisionUAV-Navigation** (`https://github.com/sidharthmohannair/VisionUAV-Navigation`).

## Military / Tactical Context
This adapter supports UAV relocalization workflows in GPS-denied airspace by matching onboard imagery against geospatial references during reconnaissance and route-correction operations.

## Adapter Class
- `VisionuavNavigationAdapter`
- `integration_id = "visionuav-navigation"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.visionuav-navigation`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local tooling and configured paths.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
