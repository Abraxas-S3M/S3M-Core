# Hugging Face Provider Runbook

## Purpose
Formalize S3M model hub and inference integration for model discovery, cache governance, and offline verification.

## Token Setup
- Optional token env var: `S3M_HUGGINGFACE_TOKEN` (or `HUGGINGFACE_TOKEN`).
- Public models can be accessed without a token; private models require Bearer auth.

## S3M Model Registry
S3M tracks 9 required models:
- `phi-3-medium`, `mixtral-8x7b`, `grok-1` (LLM core)
- `arabert`, `mt5-arabic`, `camelbert` (Arabic NLP)
- `yolov8n` (threat detection)
- `whisper-base` (command agent voice)
- `sar-ship-detect` (sensor analytics)

Grok-1 note: model payload is 300+ GB (fp16 class) and practical acquisition typically uses torrent/magnet workflow in addition to standard hub methods.

## Pre-deployment Download Strategy
1. Download all 9 registry models to `models/`.
2. Quantize edge-critical models for Jetson deployment.
   - Tactical context: quantized models preserve inference responsiveness under contested compute budgets.
3. Run model status check to verify cache completeness.

## Offline Manifest
- Generate: `adapter.generate_offline_manifest()`
- Output path: `configs/integrations/model_manifest.yaml`
- Includes file checksums for air-gapped integrity checks.

## Inference Flow
- Preferred: local model inference.
- Online fallback: Hugging Face Inference API.
- If API fails, adapter falls back to local inference-safe behavior.

## Quantization Notes
- LLMs: GPTQ/AWQ/GGUF workflows.
- Detection models: ONNX/TensorRT conversion for edge runtime.

## S3M Integration
Feeds all S3M ML layers by acting as:
- model registry source of truth,
- cache readiness gate,
- controlled inference adapter.

## Smoke Test
```bash
pytest -q packages/providers/ml-huggingface/tests/test_huggingface_adapter.py
```
