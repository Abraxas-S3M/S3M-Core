#!/bin/bash
set -euo pipefail

# S3M UNCLASSIFIED - FOUO
# Tactical context: post-train merge+quantization minimizes transfer footprint
# for rapid fielding of updated model behavior to edge inference nodes.

ENGINE="${1:-}"
if [[ -z "${ENGINE}" ]]; then
  echo "Usage: $0 <engine>" >&2
  echo "Valid engines: phi3-medium, allam, mixtral, grok1" >&2
  exit 1
fi

if [[ -z "${S3M_VAULT_IP:-}" ]]; then
  echo "ERROR: S3M_VAULT_IP is required." >&2
  exit 1
fi

case "${ENGINE}" in
  phi3-medium|allam|mixtral|grok1) ;;
  *)
    echo "ERROR: Invalid engine '${ENGINE}'." >&2
    exit 1
    ;;
esac

WORKSPACE_ROOT="/workspace"
LLAMA_CPP_ROOT="${WORKSPACE_ROOT}/llama.cpp"
BASE_DIR="${WORKSPACE_ROOT}/base_weights/${ENGINE}"
MERGED_DIR="${WORKSPACE_ROOT}/output/merged/${ENGINE}"
GGUF_DIR="${WORKSPACE_ROOT}/output/gguf/${ENGINE}"
GGUF_FP16="${GGUF_DIR}/${ENGINE}-merged-f16.gguf"
GGUF_Q4="${GGUF_DIR}/${ENGINE}-merged-q4_k_m.gguf"

adapter_dir_candidates=(
  "${WORKSPACE_ROOT}/output/adapters/${ENGINE}"
  "${WORKSPACE_ROOT}/output/adapters/${ENGINE//-/_}"
  "${WORKSPACE_ROOT}/output/adapters/${ENGINE//_/-}"
)

ADAPTER_DIR=""
for candidate in "${adapter_dir_candidates[@]}"; do
  if [[ -d "${candidate}" ]]; then
    ADAPTER_DIR="${candidate}"
    break
  fi
done

if [[ -z "${ADAPTER_DIR}" ]]; then
  echo "ERROR: Could not locate adapter directory for ${ENGINE} under /workspace/output/adapters." >&2
  exit 1
fi

MODEL_ID=""
case "${ENGINE}" in
  phi3-medium) MODEL_ID="microsoft/Phi-3-medium-4k-instruct" ;;
  allam) MODEL_ID="humain-ai/ALLaM-7B-Instruct-preview" ;;
  mixtral) MODEL_ID="mistralai/Mixtral-8x7B-Instruct-v0.1" ;;
  grok1) MODEL_ID="xai-org/grok-1" ;;
esac

BASE_SOURCE="${BASE_DIR}"
if [[ ! -d "${BASE_DIR}" ]]; then
  BASE_SOURCE="${MODEL_ID}"
fi

banner() {
  echo
  echo "=================================================================="
  echo "$1"
  echo "=================================================================="
}

banner "Step 1/4: Merge LoRA adapter into base weights with PEFT"
mkdir -p "${MERGED_DIR}" "${GGUF_DIR}"

BASE_SOURCE="${BASE_SOURCE}" ADAPTER_DIR="${ADAPTER_DIR}" MERGED_DIR="${MERGED_DIR}" python3 - <<'PY'
import os
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

base_source = os.environ["BASE_SOURCE"]
adapter_dir = os.environ["ADAPTER_DIR"]
merged_dir = os.environ["MERGED_DIR"]

tokenizer = AutoTokenizer.from_pretrained(base_source, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    base_source,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True,
)
peft_model = PeftModel.from_pretrained(model, adapter_dir)
merged_model = peft_model.merge_and_unload()
merged_model.save_pretrained(merged_dir, safe_serialization=True, max_shard_size="10GB")
tokenizer.save_pretrained(merged_dir)
print(f"Merged model saved to {merged_dir}")
PY

banner "Step 2/4: Convert merged HF model to GGUF fp16"
python3 "${LLAMA_CPP_ROOT}/convert_hf_to_gguf.py" "${MERGED_DIR}" --outfile "${GGUF_FP16}" --outtype f16

banner "Step 3/4: Quantize GGUF to Q4_K_M"
"${LLAMA_CPP_ROOT}/build/bin/llama-quantize" "${GGUF_FP16}" "${GGUF_Q4}" Q4_K_M

banner "Step 4/4: Push quantized GGUF + adapters to vault"
rsync -avz "${GGUF_Q4}" "s3m-sync@${S3M_VAULT_IP}::s3m-weights/quantized/${ENGINE}/"
rsync -avz "${ADAPTER_DIR}/" "s3m-sync@${S3M_VAULT_IP}::s3m-weights/adapters/${ENGINE}/"

banner "Cleaning fp16 intermediate artifacts to save disk"
rm -f "${GGUF_FP16}"
rm -rf "${MERGED_DIR}"

echo "Completed merge and quantization for ${ENGINE}."
echo "Quantized output: ${GGUF_Q4}"
