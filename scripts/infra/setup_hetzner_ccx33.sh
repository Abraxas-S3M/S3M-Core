#!/bin/bash
set -euo pipefail

# S3M UNCLASSIFIED - FOUO
# Tactical context: this node orchestrates persistent CPU-side adaptation and
# dispatches GPU tasks so distributed training remains available 24/7.

if [[ -z "${S3M_VAULT_IP:-}" ]]; then
  echo "ERROR: S3M_VAULT_IP is required." >&2
  exit 1
fi

S3M_ROOT="/opt/s3m"
VENV_PATH="${S3M_ROOT}/venv"
BIN_PATH="${S3M_ROOT}/bin"
LOG_PATH="${S3M_ROOT}/logs"

banner() {
  echo
  echo "=================================================================="
  echo "$1"
  echo "=================================================================="
}

install_packages() {
  banner "Installing Hetzner CCX33 system dependencies"
  sudo apt-get update
  sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    rsync \
    cron

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now cron
  fi
}

create_directories() {
  banner "Creating /opt/s3m working directories"
  sudo mkdir -p \
    "${S3M_ROOT}/adapters" \
    "${S3M_ROOT}/datasets" \
    "${S3M_ROOT}/gradients" \
    "${S3M_ROOT}/pseudo_labels" \
    "${S3M_ROOT}/models/phi3-medium" \
    "${BIN_PATH}" \
    "${LOG_PATH}"
  sudo chown -R "$(id -u)":"$(id -g)" "${S3M_ROOT}"
}

setup_venv() {
  banner "Creating Python 3.11 virtual environment and installing CPU stack"
  if [[ ! -d "${VENV_PATH}" ]]; then
    python3.11 -m venv "${VENV_PATH}"
  fi

  # shellcheck disable=SC1091
  source "${VENV_PATH}/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install \
    numpy \
    pyyaml \
    pydantic \
    fastapi \
    uvicorn \
    grpcio \
    huggingface-hub \
    requests
  CMAKE_ARGS="-DGGML_CUDA=OFF" LLAMA_CPP_FORCE_CMAKE=1 python -m pip install llama-cpp-python
}

pull_phi3_quantized() {
  banner "Pulling Phi-3 Medium Q4 GGUF from vault"
  mkdir -p "${S3M_ROOT}/models/phi3-medium"

  rsync -avz --prune-empty-dirs \
    --include="*/" \
    --include="*Q4*.gguf" \
    --exclude="*" \
    "s3m-sync@${S3M_VAULT_IP}::s3m-weights/quantized/phi3-medium/" \
    "${S3M_ROOT}/models/phi3-medium/" || true

  if ! compgen -G "${S3M_ROOT}/models/phi3-medium/*.gguf" >/dev/null; then
    echo "No Q4 file matched, pulling available GGUF files as fallback."
    rsync -avz --prune-empty-dirs \
      --include="*/" \
      --include="*.gguf" \
      --exclude="*" \
      "s3m-sync@${S3M_VAULT_IP}::s3m-weights/quantized/phi3-medium/" \
      "${S3M_ROOT}/models/phi3-medium/" || true
  fi
}

create_sync_scripts() {
  banner "Creating cron sync scripts"
  cat >"${BIN_PATH}/sync_adapters.sh" <<EOF
#!/bin/bash
set -euo pipefail
rsync -avz --delete "s3m-sync@${S3M_VAULT_IP}::s3m-weights/adapters/" "${S3M_ROOT}/adapters/"
EOF

  cat >"${BIN_PATH}/push_gradients.sh" <<EOF
#!/bin/bash
set -euo pipefail
rsync -avz "${S3M_ROOT}/gradients/" "s3m-sync@${S3M_VAULT_IP}::s3m-weights/manifests/hetzner-gradients/"
EOF

  cat >"${BIN_PATH}/push_pseudo_labels.sh" <<EOF
#!/bin/bash
set -euo pipefail
rsync -avz "${S3M_ROOT}/pseudo_labels/" "s3m-sync@${S3M_VAULT_IP}::s3m-weights/datasets/pseudo-labels/"
EOF

  chmod +x "${BIN_PATH}/sync_adapters.sh" "${BIN_PATH}/push_gradients.sh" "${BIN_PATH}/push_pseudo_labels.sh"
}

configure_cron() {
  banner "Installing cron jobs"
  local tmp_cron
  tmp_cron="$(mktemp)"
  (crontab -l 2>/dev/null || true) | rg -v "s3m-(sync-adapters|push-gradients|push-pseudo-labels)" > "${tmp_cron}" || true

  cat >> "${tmp_cron}" <<EOF
*/30 * * * * ${BIN_PATH}/sync_adapters.sh >> ${LOG_PATH}/s3m-sync-adapters.log 2>&1 # s3m-sync-adapters
*/30 * * * * ${BIN_PATH}/push_gradients.sh >> ${LOG_PATH}/s3m-push-gradients.log 2>&1 # s3m-push-gradients
0 */2 * * * ${BIN_PATH}/push_pseudo_labels.sh >> ${LOG_PATH}/s3m-push-pseudo-labels.log 2>&1 # s3m-push-pseudo-labels
EOF

  crontab "${tmp_cron}"
  rm -f "${tmp_cron}"
}

create_systemd_services() {
  banner "Creating systemd services (s3m-cpu-train, s3m-orchestrator)"

  cat >/tmp/s3m-cpu-train.service <<EOF
[Unit]
Description=S3M CPU Training Loop Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/workspace
Environment=S3M_VAULT_IP=${S3M_VAULT_IP}
ExecStart=/bin/bash -lc 'source ${VENV_PATH}/bin/activate && if [ -f /workspace/scripts/training/cpu_training_loop.py ]; then python /workspace/scripts/training/cpu_training_loop.py; else while true; do echo "[s3m-cpu-train] waiting for cpu_training_loop.py"; sleep 300; done; fi'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  cat >/tmp/s3m-orchestrator.service <<EOF
[Unit]
Description=S3M GPU Orchestrator Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/workspace
Environment=S3M_VAULT_IP=${S3M_VAULT_IP}
ExecStart=/bin/bash -lc 'source ${VENV_PATH}/bin/activate && if [ -f /workspace/scripts/training/gpu_orchestrator.py ]; then python /workspace/scripts/training/gpu_orchestrator.py; else while true; do echo "[s3m-orchestrator] waiting for gpu_orchestrator.py"; sleep 300; done; fi'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  sudo cp /tmp/s3m-cpu-train.service /etc/systemd/system/s3m-cpu-train.service
  sudo cp /tmp/s3m-orchestrator.service /etc/systemd/system/s3m-orchestrator.service
  rm -f /tmp/s3m-cpu-train.service /tmp/s3m-orchestrator.service

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl daemon-reload
    sudo systemctl enable s3m-cpu-train s3m-orchestrator
  fi
}

print_summary() {
  banner "Hetzner setup summary"
  echo "Vault endpoint: ${S3M_VAULT_IP}"
  echo "S3M root: ${S3M_ROOT}"
  echo "Venv: ${VENV_PATH}"
  echo "Phi-3 quantized model path: ${S3M_ROOT}/models/phi3-medium"
  echo "Cron jobs:"
  crontab -l | rg "s3m-(sync-adapters|push-gradients|push-pseudo-labels)" || true
  echo "Systemd units installed:"
  echo "  /etc/systemd/system/s3m-cpu-train.service"
  echo "  /etc/systemd/system/s3m-orchestrator.service"
}

main() {
  install_packages
  create_directories
  setup_venv
  pull_phi3_quantized
  create_sync_scripts
  configure_cron
  create_systemd_services
  print_summary
}

main "$@"
