# TensorRT-Edge-LLM Integration

## Purpose

This adapter wraps TensorRT-Edge-LLM so S3M can validate embedded LLM/VLM runtime readiness for navigation decision support.

Military/tactical context: it supports low-latency onboard language/vision inference for route adaptation when cloud assistance is unavailable or denied.

## Adapter Class

- `TensorrtEdgeLlmAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.navigation.tensorrt-edge-llm`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local runtime command/module checks and readiness output

## Manifest

Integration metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
