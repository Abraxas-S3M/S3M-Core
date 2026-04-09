# battle-simulator Integration

## Purpose

This adapter wraps the `battle-simulator` repository for S3M military planning
workflows.

Military/tactical context: it supports offline battle-map rehearsal so planners
can evaluate node positioning and sustainment risk before committing force
movements.

## Adapter Class

- `BattleSimulatorAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.battle-simulator`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local binary/path readiness and reports adapter
  execution readiness

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
