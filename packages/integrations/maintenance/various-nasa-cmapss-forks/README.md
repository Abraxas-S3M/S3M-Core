# Various NASA CMAPSS forks Integration

## Purpose

This adapter wraps multiple NASA CMAPSS fork repositories used for turbofan
degradation simulation and predictive maintenance experiments.

Military/tactical context: aviation maintenance planners can rehearse
engine-readiness prioritization using deterministic offline outputs.

## Adapter Class

- `VariousNasaCmapssForksAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.maintenance.various-nasa-cmapss-forks`

## Operational Modes

- **Airgapped mode**: `execute()` returns fixture data from
  `fixtures/sample_response.json`.
- **Online mode**: checks local tools/path configuration only; no external APIs.

## Manifest

Integration metadata is maintained in `manifest.yaml` and surfaced via
`get_manifest()`.
