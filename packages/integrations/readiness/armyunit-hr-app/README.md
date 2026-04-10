# ArmyUnit-HR-App Integration

## Purpose

This adapter wraps the ArmyUnit-HR-App repository for S3M unit HR and readiness workflows.

Military/tactical context: it provides an offline-safe interface for personnel status accounting and deployability monitoring to support commander staffing decisions.

## Adapter Class

- `ArmyunitHrAppAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.armyunit-hr-app`

## Operational Modes

- **Airgapped mode**: deterministic replay from `fixtures/sample_response.json`
- **Online mode**: checks local runtime tooling or configured path availability

## Manifest

Metadata is sourced from `manifest.yaml` and returned by `get_manifest()`.
