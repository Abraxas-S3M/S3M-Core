# onnxruntime Integration

## Purpose

This adapter wraps ONNX Runtime so S3M navigation pipelines can evaluate local acceleration readiness without requiring external connectivity.

Military/tactical context: it supports deterministic edge inference validation for route planning, guidance, and contested-environment autonomy drills.

## Adapter Class

- `OnnxruntimeAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.onnxruntime`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/module checks and readiness output only

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
