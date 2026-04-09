# tvm Integration

## Purpose

This adapter wraps Apache TVM for S3M navigation workloads so model compilation readiness can be validated locally and reproducibly.

Military/tactical context: it supports edge-compiler preparation for mission-critical autonomy where CPU/GPU/NPU availability varies by platform and theater.

## Adapter Class

- `TvmAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.tvm`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local compiler/module checks and readiness output only

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
