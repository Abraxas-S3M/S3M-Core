# VehicleDetection (SAR Small Object) Integration

S3M dataset-domain wrapper for **VehicleDetection (SAR Small Object)**.

## Military / Tactical Context
This adapter supports ISR training pipelines where radar imagery is used to
detect small vehicle signatures over broad, remote areas. It preserves mission
readiness in disconnected environments through deterministic fixture fallback.

## Adapter Class
- `VehicledetectionsarSmallObjectAdapter`
- `integration_id = "vehicledetection-sar-small-object"`
- `domain = "datasets"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks mirrored SAR dataset paths and local tooling.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
