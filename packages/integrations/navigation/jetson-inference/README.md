# jetson-inference Integration

## Purpose

This adapter wraps jetson-inference for S3M so Jetson vision runtime readiness can be validated in a consistent integration contract.

Military/tactical context: it supports onboard perception rehearsal for navigation safety and obstacle/threat awareness in disconnected missions.

## Adapter Class

- `JetsonInferenceAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.jetson-inference`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local command/path checks and readiness output

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
