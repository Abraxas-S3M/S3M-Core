# SDAIA ALLaM Runbook

## Role in S3M
SDAIA ALLaM is the sovereign Arabic backbone in S3M Quad-LLM operations. This provider wraps the existing local ALLaM runtime with formal government integration controls for model governance and reporting.

## Model Versions and Quantization
- ALLaM-7B (base)
- ALLaM-7B-Chat (instruction/chat)

Jetson AGX Orin guidance:
- fp16: 14 GB VRAM
- int8: 7 GB VRAM (recommended)
- int4: 4 GB VRAM (quality tradeoff)

## VRAM Budget Reference
- ALLaM int8: 7 GB
- Phi-3 Medium int4: 10 GB
- Mixtral 8x7B int4: 28 GB
- Grok-1 int4: 85 GB
- Combined quad-engine Q4 budget: ~128 GB VRAM class runtime.

## Arabic Military Benchmark Suite
- Summarization quality for Arabic tactical traffic
- Named-entity extraction (units/locations)
- Arabic-English military phrase translation
- Command intent classification

## S3M Usage Contexts
1. Phase 14 secure comms summarization
2. Phase 19 Arabic intelligence briefing generation
3. Arabic entity extraction in comms/intel workflows
4. Arabic command parsing in tactical C2
5. Arabic-English military translation support
6. Arabic threat classification flows

## Integration Notes
- Wrapper over existing `src/llm_core` ALLaM engine (no replacement)
- Inference remains local only
- SDAIA API endpoints are placeholders pending formal government coordination

## Usage Reporting
Track token volume, call counts, latency, and context usage breakdown for sovereign AI governance reporting.

## Air-Gapped Operation
Model weights remain on local Jetson storage. No API connectivity is required for inference.

## Smoke Test
```bash
python3 -m pytest -q packages/providers/sovereign-sdaia-allam/tests/test_sdaia_allam_adapter.py
```
