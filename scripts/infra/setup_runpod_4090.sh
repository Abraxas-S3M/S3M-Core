#!/bin/bash
set -euo pipefail

# S3M UNCLASSIFIED - FOUO
# Tactical context: this script hardens each transient GPU pod into a
# deterministic training node for rapid adapter generation in contested links.

for required_key in S3M_STORAGE_ACCESS_KEY S3M_STORAGE_SECRET_KEY S3M_STORAGE_BUCKET_NAME S3M_STORAGE_ENDPOINT; do
  if [[ -z "${!required_key:-}" ]]; then
    echo "ERROR: ${required_key} is required." >&2
    exit 1
  fi
done

if [[ -z "${S3M_TARGET_ENGINE:-}" ]]; then
  echo "ERROR: S3M_TARGET_ENGINE is required." >&2
  exit 1
fi

case "${S3M_TARGET_ENGINE}" in
  phi3-medium|mistral-7b|mixtral|allam) ;;
  *)
    echo "ERROR: S3M_TARGET_ENGINE must be one of: phi3-medium, mistral-7b, mixtral, allam" >&2
    exit 1
    ;;
esac

if [[ "$(printf '%s' "${S3M_TARGET_ENGINE}" | tr '[:upper:]' '[:lower:]')" == *grok* ]]; then
  echo "ERROR: Grok-family engines are blocked from RunPod object storage sync policy." >&2
  exit 1
fi

WORKSPACE_ROOT="/workspace"
VENV_PATH="${WORKSPACE_ROOT}/.venv-runpod4090"
BASE_ROOT="${WORKSPACE_ROOT}/base_weights/${S3M_TARGET_ENGINE}"
DATASET_ROOT="${WORKSPACE_ROOT}/datasets/${S3M_TARGET_ENGINE}"
ADAPTER_ROOT="${WORKSPACE_ROOT}/output/adapters/${S3M_TARGET_ENGINE}"
CHECKPOINT_ROOT="${WORKSPACE_ROOT}/checkpoints"
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
  apt-get install -y build-essential cmake git python3-pip python3-venv
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
    huggingface-hub \
    boto3 \
    pyyaml
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
  banner "Syncing base weights and datasets from Hetzner Object Storage"
  if [[ "$(printf '%s' "${S3M_TARGET_ENGINE}" | tr '[:upper:]' '[:lower:]')" == *grok* ]]; then
    echo "ERROR: Grok-family engine sync is blocked by policy." >&2
    exit 1
  fi

  mkdir -p "${BASE_ROOT}" "${DATASET_ROOT}" "${ADAPTER_ROOT}" "${CHECKPOINT_ROOT}"
  # shellcheck disable=SC1091
  source "${VENV_PATH}/bin/activate"

  export BASE_ROOT DATASET_ROOT ADAPTER_ROOT CHECKPOINT_ROOT
  python - <<'PY'
import os

from src.storage.object_storage import ObjectStorageConnector
from src.storage.vault_paths import VaultPaths

engine = os.environ["S3M_TARGET_ENGINE"].strip()
if "grok" in engine.lower():
    raise SystemExit("Grok-family engine sync is blocked by policy.")

connector = ObjectStorageConnector(
    access_key=os.environ["S3M_STORAGE_ACCESS_KEY"],
    secret_key=os.environ["S3M_STORAGE_SECRET_KEY"],
    bucket_name=os.environ["S3M_STORAGE_BUCKET_NAME"],
    endpoint=os.environ["S3M_STORAGE_ENDPOINT"],
)

base_root = os.environ["BASE_ROOT"]
dataset_root = os.environ["DATASET_ROOT"]
adapter_root = os.environ["ADAPTER_ROOT"]
tracks = ("saudi_mod", "ukraine_mod", "nato", "shared")

connector.sync_prefix_to_local(prefix=f"base-weights/{engine}/", local_dir=base_root)
for track in tracks:
    connector.sync_prefix_to_local(
        prefix=VaultPaths.dataset_scenarios(track),
        local_dir=f"{dataset_root}/{track}/scenarios",
    )
    connector.sync_prefix_to_local(
        prefix=VaultPaths.adapters(engine, track=track),
        local_dir=f"{adapter_root}/{track}",
    )
print("Hetzner Object Storage pull complete.")
PY
}

push_to_vault() {
  banner "Pushing training artifacts to Hetzner Object Storage"
  if [[ "$(printf '%s' "${S3M_TARGET_ENGINE}" | tr '[:upper:]' '[:lower:]')" == *grok* ]]; then
    echo "ERROR: Grok-family engine push is blocked by policy." >&2
    exit 1
  fi

  # shellcheck disable=SC1091
  source "${VENV_PATH}/bin/activate"
  export BASE_ROOT DATASET_ROOT ADAPTER_ROOT CHECKPOINT_ROOT
  python - <<'PY'
import os

from src.storage.object_storage import ObjectStorageConnector
from src.storage.vault_paths import VaultPaths

engine = os.environ["S3M_TARGET_ENGINE"].strip()
if "grok" in engine.lower():
    raise SystemExit("Grok-family engine push is blocked by policy.")

connector = ObjectStorageConnector(
    access_key=os.environ["S3M_STORAGE_ACCESS_KEY"],
    secret_key=os.environ["S3M_STORAGE_SECRET_KEY"],
    bucket_name=os.environ["S3M_STORAGE_BUCKET_NAME"],
    endpoint=os.environ["S3M_STORAGE_ENDPOINT"],
)

adapter_root = os.environ["ADAPTER_ROOT"]
checkpoint_root = os.environ["CHECKPOINT_ROOT"]

connector.sync_local_to_prefix(local_dir=adapter_root, prefix=VaultPaths.adapters(engine))
connector.sync_local_to_prefix(
    local_dir=checkpoint_root,
    prefix=VaultPaths.checkpoints("runpod", engine_id=engine),
)
print("Hetzner Object Storage push complete.")
PY
}

run_training_and_push() {
  if [[ -z "${S3M_TRAINING_CMD:-}" ]]; then
    echo "No S3M_TRAINING_CMD provided; skipping training execution and push."
    return
  fi
  banner "Running training command and pushing artifacts"
  # shellcheck disable=SC1091
  source "${VENV_PATH}/bin/activate"
  (cd "${WORKSPACE_ROOT}" && bash -lc "${S3M_TRAINING_CMD}")
  push_to_vault
}

print_ready() {
  banner "RunPod 4090 node ready"
  echo "Target engine: ${S3M_TARGET_ENGINE}"
  echo "Object storage bucket: ${S3M_STORAGE_BUCKET_NAME}"
  echo "Object storage endpoint: ${S3M_STORAGE_ENDPOINT}"
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
  run_training_and_push
}

main "$@"
