# Onnxruntime-TensorRT Integration

## Purpose

This adapter wraps Onnxruntime-TensorRT optimization workflows so S3M can validate local ONNX-to-TensorRT readiness for navigation models.

Military/tactical context: it supports quantized edge deployment checks that reduce latency and power draw for autonomous navigation during prolonged operations.

## Adapter Class

- `OnnxruntimeTensorrtAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.onnxruntime-tensorrt`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local module/tool checks and readiness output

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
