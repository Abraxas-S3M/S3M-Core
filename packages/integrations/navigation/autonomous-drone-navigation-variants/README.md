# Autonomous-drone-navigation (variants) Integration

S3M navigation-domain adapter for GPS-denied drone navigation topics and related repositories (`https://github.com/topics/gps-denied`).

## Military / Tactical Context
This adapter supports mission rehearsal for UAV units operating in GPS-denied and electronically contested zones, where optical flow and fused localization are required to maintain route continuity.

## Adapter Class
- `AutonomousDroneNavigationvariantsAdapter`
- `integration_id = "autonomous-drone-navigation-variants"`
- `domain = "navigation"`
- Logger: `s3m.integrations.navigation.autonomous-drone-navigation-variants`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local runtime signals and configured binaries.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
