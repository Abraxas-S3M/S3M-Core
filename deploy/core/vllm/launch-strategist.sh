#!/usr/bin/env bash
# Reference launch script for core-tier vLLM strategist (no weights included).
set -euo pipefail

MODEL_PATH="${MODEL_PATH:-/var/lib/s3m/weights/STRATEGIST_MOE_PLACEHOLDER}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
TENSOR_PARALLEL="${TENSOR_PARALLEL:-8}"

exec python -m vllm.entrypoints.openai.api_server \
  --model "${MODEL_PATH}" \
  --host "${VLLM_HOST}" \
  --port "${VLLM_PORT}" \
  --tensor-parallel-size "${TENSOR_PARALLEL}" \
  --served-model-name strategist-moe
