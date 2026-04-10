# OpenXE-org/OpenXE Integration

S3M maintenance-domain wrapper for **OpenXE-org/OpenXE** procurement, inventory,
and maintenance-planning workflows.

## Military / Tactical Context
This adapter supports sustainment command by linking maintenance demand with
procurement status to reduce readiness gaps in disconnected theaters.

## Adapter Class
- `OpenxeOrgopenxeAdapter`
- `integration_id = "openxe-org-openxe"`
- `domain = "maintenance"`
- Logger: `s3m.integrations.maintenance.openxe-org-openxe`

## Behavior
- `get_manifest()` loads metadata from `manifest.yaml`.
- `validate_availability()` checks local binaries or configured local paths only.
- `execute()` returns deterministic fixture output in airgapped mode.

## Airgapped Fixture
Fixture file: `fixtures/sample_response.json`
