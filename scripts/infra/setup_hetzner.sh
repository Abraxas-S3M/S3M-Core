#!/bin/bash
set -euo pipefail

# S3M UNCLASSIFIED - FOUO
# Tactical context: this provisioning flow turns a persistent Hetzner CPU node
# into a resilient sync-and-train platform that can keep adapting doctrine even
# when links are degraded and synchronization retries are required.

S3M_ROOT="/opt/s3m"
VENV_PATH="${S3M_ROOT}/venv"
BIN_PATH="${S3M_ROOT}/bin"
LOG_PATH="${S3M_ROOT}/logs"
WORKSPACE_ROOT="/workspace"
REPO_SRC="${S3M_REPO_SRC:-$(pwd)}"
TRACKS=("saudi_mod" "ukraine_mod" "nato" "shared")

banner() {
  echo
  echo "=================================================================="
  echo "$1"
  echo "=================================================================="
}

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    echo "ERROR: ${key} is required." >&2
    exit 1
  fi
}

install_packages() {
  banner "Installing Hetzner Object Storage system dependencies"
  sudo apt-get update
  sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    python3.11 \
    python3.11-dev \
    python3.11-venv
}

create_directories() {
  banner "Creating /opt/s3m working directories"
  sudo mkdir -p \
    "${S3M_ROOT}/adapters" \
    "${S3M_ROOT}/datasets" \
    "${S3M_ROOT}/gradients" \
    "${S3M_ROOT}/pseudo_labels" \
    "${S3M_ROOT}/models/phi3-medium" \
    "${S3M_ROOT}/models/mistral-7b" \
    "${S3M_ROOT}/gui-snapshots" \
    "${S3M_ROOT}/state/training/cloud_cpu/metrics" \
    "${BIN_PATH}" \
    "${LOG_PATH}"

  for track in "${TRACKS[@]}"; do
    sudo mkdir -p \
      "${S3M_ROOT}/state/training/cloud_cpu/tracks/${track}/scenarios" \
      "${S3M_ROOT}/state/training/cloud_cpu/tracks/${track}/checkpoints"
  done

  sudo chown -R "$(id -u)":"$(id -g)" "${S3M_ROOT}"
}

setup_venv() {
  banner "Creating Python 3.11 virtual environment and installing dependencies"
  if [[ ! -d "${VENV_PATH}" ]]; then
    python3.11 -m venv "${VENV_PATH}"
  fi

  # shellcheck disable=SC1091
  source "${VENV_PATH}/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install \
    boto3 \
    pyyaml \
    psutil \
    numpy \
    pydantic \
    fastapi \
    uvicorn \
    grpcio \
    huggingface-hub \
    requests
  CMAKE_ARGS="-DGGML_CUDA=OFF" LLAMA_CPP_FORCE_CMAKE=1 python -m pip install llama-cpp-python
}

copy_repo_to_workspace() {
  banner "Copying S3M-Core repository to /workspace"
  sudo mkdir -p "${WORKSPACE_ROOT}"
  sudo chown -R "$(id -u)":"$(id -g)" "${WORKSPACE_ROOT}"

  if [[ "$(realpath "${REPO_SRC}")" == "$(realpath "${WORKSPACE_ROOT}")" ]]; then
    echo "Repository source already /workspace; skipping copy."
    return
  fi

  cp -a "${REPO_SRC}/." "${WORKSPACE_ROOT}/"
}

write_env_file() {
  banner "Writing /workspace/.env from Hetzner Object Storage credentials"
  require_env "S3M_STORAGE_ACCESS_KEY"
  require_env "S3M_STORAGE_SECRET_KEY"
  require_env "S3M_STORAGE_BUCKET_NAME"
  require_env "S3M_STORAGE_ENDPOINT"

  cat >"${WORKSPACE_ROOT}/.env" <<EOF
S3M_STORAGE_ACCESS_KEY=${S3M_STORAGE_ACCESS_KEY}
S3M_STORAGE_SECRET_KEY=${S3M_STORAGE_SECRET_KEY}
S3M_STORAGE_BUCKET_NAME=${S3M_STORAGE_BUCKET_NAME}
S3M_STORAGE_ENDPOINT=${S3M_STORAGE_ENDPOINT}
EOF
  chmod 600 "${WORKSPACE_ROOT}/.env"
}

initial_model_sync() {
  banner "Initial Hetzner Object Storage pull for Phi-3 and Mistral quantized weights"

  # shellcheck disable=SC1091
  source "${VENV_PATH}/bin/activate"
  set -a
  # shellcheck disable=SC1091
  source "${WORKSPACE_ROOT}/.env"
  set +a

  python - <<'PY'
import os

from src.storage.object_storage import ObjectStorageConnector
from src.storage.vault_paths import VaultPaths

blocked_tokens = ("grok", "grok-300b", "base-weights/grok-300b", "quantized/grok-300b")
engines = ("phi3-medium", "mistral-7b")
connector = ObjectStorageConnector(
    access_key=os.environ["S3M_STORAGE_ACCESS_KEY"],
    secret_key=os.environ["S3M_STORAGE_SECRET_KEY"],
    bucket_name=os.environ["S3M_STORAGE_BUCKET_NAME"],
    endpoint=os.environ["S3M_STORAGE_ENDPOINT"],
)
for engine_id in engines:
    prefix = VaultPaths.quantized_engine(engine_id)
    if any(token in prefix.lower() for token in blocked_tokens):
        raise SystemExit(f"Blocked by policy: refusing to pull {prefix}")
    connector.sync_prefix_to_local(prefix=prefix, local_dir=f"/opt/s3m/models/{engine_id}")
print("Initial quantized model sync completed.")
PY
}

install_systemd_units() {
  banner "Installing systemd units and timer"

  cat >/tmp/s3m-storage-sync.service <<EOF
[Unit]
Description=S3M Hetzner Object Storage Sync Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
WorkingDirectory=${WORKSPACE_ROOT}
EnvironmentFile=${WORKSPACE_ROOT}/.env
ExecStart=/bin/bash -lc 'source ${VENV_PATH}/bin/activate && python ${WORKSPACE_ROOT}/scripts/infra/storage_sync_daemon.py --config ${WORKSPACE_ROOT}/configs/deployment/object_storage.yaml --once'
EOF

  cat >/tmp/s3m-storage-sync.timer <<EOF
[Unit]
Description=Run S3M Hetzner Object Storage sync every 30 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true
Unit=s3m-storage-sync.service

[Install]
WantedBy=timers.target
EOF

  cat >/tmp/s3m-cpu-train.service <<EOF
[Unit]
Description=S3M CPU Training Loop Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${WORKSPACE_ROOT}
EnvironmentFile=${WORKSPACE_ROOT}/.env
Environment=DEPLOYMENT_MODE=cloud_cpu_demo
ExecStart=/bin/bash -lc 'source ${VENV_PATH}/bin/activate && if [ -f ${WORKSPACE_ROOT}/scripts/training/cpu_training_loop.py ]; then python ${WORKSPACE_ROOT}/scripts/training/cpu_training_loop.py; else while true; do echo "[s3m-cpu-train] waiting for cpu_training_loop.py"; sleep 300; done; fi'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  cat >/tmp/s3m-api-server.service <<EOF
[Unit]
Description=S3M API Server (GUI Bridge)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${WORKSPACE_ROOT}
EnvironmentFile=${WORKSPACE_ROOT}/.env
Environment=DEPLOYMENT_MODE=cloud_cpu_demo
Environment=S3M_DEVICE=cpu
ExecStart=/bin/bash -lc 'source ${VENV_PATH}/bin/activate && python ${WORKSPACE_ROOT}/scripts/start_api.py'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  sudo cp /tmp/s3m-storage-sync.service /etc/systemd/system/s3m-storage-sync.service
  sudo cp /tmp/s3m-storage-sync.timer /etc/systemd/system/s3m-storage-sync.timer
  sudo cp /tmp/s3m-cpu-train.service /etc/systemd/system/s3m-cpu-train.service
  sudo cp /tmp/s3m-api-server.service /etc/systemd/system/s3m-api-server.service
  rm -f \
    /tmp/s3m-storage-sync.service \
    /tmp/s3m-storage-sync.timer \
    /tmp/s3m-cpu-train.service \
    /tmp/s3m-api-server.service

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl daemon-reload
    sudo systemctl enable s3m-cpu-train s3m-api-server s3m-storage-sync.timer
    sudo systemctl restart s3m-cpu-train s3m-api-server
    sudo systemctl start s3m-storage-sync.service || true
    sudo systemctl start s3m-storage-sync.timer
  fi
}

print_summary() {
  banner "Hetzner Object Storage setup summary"
  echo "S3M root: ${S3M_ROOT}"
  echo "Workspace root: ${WORKSPACE_ROOT}"
  echo "Venv: ${VENV_PATH}"
  echo "Storage sync service: /etc/systemd/system/s3m-storage-sync.service"
  echo "Storage sync timer: /etc/systemd/system/s3m-storage-sync.timer"
  echo "CPU train service: /etc/systemd/system/s3m-cpu-train.service"
  echo "API server service: /etc/systemd/system/s3m-api-server.service"
}

main() {
  install_packages
  create_directories
  setup_venv
  copy_repo_to_workspace
  write_env_file
  initial_model_sync
  install_systemd_units
  print_summary
}

main "$@"
