# ArmyManagementSystem Integration

## Purpose

This adapter wraps
[ArmyManagementSystem](https://github.com/christos-pelekis/ArmyManagementSystem)
for S3M maintenance coordination across personnel and assets.

Military/tactical context: headquarters can review maintenance posture,
assignment status, and force-support bottlenecks while fully airgapped.

## Adapter Class

- `ArmymanagementsystemAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.maintenance.armymanagementsystem`

## Operational Modes

- **Airgapped mode**: `execute()` returns deterministic fixture payloads from
  `fixtures/sample_response.json`.
- **Online mode**: performs local runtime checks only; no external API calls.

## Manifest

Metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
