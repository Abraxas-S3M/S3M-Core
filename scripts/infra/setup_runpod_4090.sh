#!/bin/bash
set -euo pipefail

# S3M UNCLASSIFIED - FOUO
# Tactical context: this script hardens each transient GPU pod into a
# deterministic training node for rapid adapter generation in contested links.

if [[ -z "${S3M_VAULT_IP:-}" ]]; then
  echo "ERROR: S3M_VAULT_IP is required." >&2
  exit 1
fi

if [[ -z "${S3M_TARGET_ENGINE:-}" ]]; then
  echo "ERROR: S3M_TARGET_ENGINE is required." >&2
  exit 1
fi

case "${S3M_TARGET_ENGINE}" in
  phi3-medium|grok1|mixtral|allam) ;;
  *)
    echo "ERROR: S3M_TARGET_ENGINE must be one of: phi3-medium, grok1, mixtral, allam" >&2
    exit 1
    ;;
esac

WORKSPACE_ROOT="/workspace"
VENV_PATH="${WORKSPACE_ROOT}/.venv-runpod4090"
BASE_ROOT="${WORKSPACE_ROOT}/base_weights/${S3M_TARGET_ENGINE}"
DATASET_ROOT="${WORKSPACE_ROOT}/datasets/${S3M_TARGET_ENGINE}"
ADAPTER_ROOT="${WORKSPACE_ROOT}/output/adapters/${S3M_TARGET_ENGINE}"
LLAMA_CPP_DIR="${WORKSPACE_ROOT}/llama.cpp"

banner() {
  echo
  echo "=================================================================="
  echo "$1"
  echo "=================================================================="
}

verify_gpu() {
  banner "Verifying NVIDIA GPU availability"
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "ERROR: nvidia-smi not found; GPU runtime is unavailable." >&2
    exit 1
  fi
  nvidia-smi
}

install_system_deps() {
  banner "Installing system dependencies"
  apt-get update
  apt-get install -y build-essential cmake git python3-pip python3-venv rsync
}

install_training_stack() {
  banner "Installing training stack (torch cu121 + HF ecosystem)"
  if [[ ! -d "${VENV_PATH}" ]]; then
    python3 -m venv "${VENV_PATH}"
  fi

  # shellcheck disable=SC1091
  source "${VENV_PATH}/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
  python -m pip install \
    transformers \
    accelerate \
    datasets \
    peft \
    bitsandbytes \
    unsloth \
    trl \
    huggingface-hub
}

build_llama_cpp_cuda() {
  banner "Building llama.cpp with CUDA support"
  if [[ ! -d "${LLAMA_CPP_DIR}/.git" ]]; then
    git clone https://github.com/ggerganov/llama.cpp.git "${LLAMA_CPP_DIR}"
  fi

  cmake -S "${LLAMA_CPP_DIR}" -B "${LLAMA_CPP_DIR}/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
  cmake --build "${LLAMA_CPP_DIR}/build" --config Release -j"$(nproc)"
}

sync_from_vault() {
  banner "Syncing base weights, datasets, and adapters from vault"
  mkdir -p "${BASE_ROOT}" "${DATASET_ROOT}" "${ADAPTER_ROOT}"

  rsync -avz --delete \
    "s3m-sync@${S3M_VAULT_IP}::s3m-weights/base/${S3M_TARGET_ENGINE}/" \
    "${BASE_ROOT}/"

  rsync -avz --delete \
    "s3m-sync@${S3M_VAULT_IP}::s3m-weights/datasets/${S3M_TARGET_ENGINE}/" \
    "${DATASET_ROOT}/" || true

  rsync -avz --delete \
    "s3m-sync@${S3M_VAULT_IP}::s3m-weights/adapters/${S3M_TARGET_ENGINE}/" \
    "${ADAPTER_ROOT}/" || true
}

print_ready() {
  banner "RunPod 4090 node ready"
  echo "Target engine: ${S3M_TARGET_ENGINE}"
  echo "Vault: ${S3M_VAULT_IP}"
  echo "Python venv: ${VENV_PATH}"
  echo "Base weights path: ${BASE_ROOT}"
  echo "Datasets path: ${DATASET_ROOT}"
  echo "Adapters path: ${ADAPTER_ROOT}"
  echo "llama.cpp binaries path: ${LLAMA_CPP_DIR}/build/bin"
}

main() {
  verify_gpu
  install_system_deps
  install_training_stack
  build_llama_cpp_cuda
  sync_from_vault
  print_ready
}

main "$@"
