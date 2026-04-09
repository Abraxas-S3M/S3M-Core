# Military Target & Equipment Detection Integration

S3M dataset-domain wrapper for **Military Target & Equipment Detection**.

## Military / Tactical Context
This adapter supports battlefield perception rehearsal by exposing a standardized
dataset interface for small-arms, armored, and personnel detection workflows.
It is designed for sovereign operation on disconnected training infrastructure.

## Adapter Class
- `MilitaryTargetEquipmentAdapter`
- `integration_id = "military-target-&-equipment-detection"`
- `domain = "datasets"`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks for local YOLO tooling or mirrored dataset paths.
- `execute()` returns deterministic fixture data in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
