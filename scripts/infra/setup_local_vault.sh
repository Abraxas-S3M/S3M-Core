#!/bin/bash
set -euo pipefail

# S3M UNCLASSIFIED - FOUO
# Tactical context: this host is the authoritative local "Weight Vault" that
# stages all model artifacts for disconnected military edge deployments.

WEIGHTS_ROOT="${S3M_WEIGHTS_ROOT:-/mnt/s3m-weights}"
KEY_PATH="${S3M_SYNC_KEY_PATH:-${WEIGHTS_ROOT}/.keys/s3m_sync_ed25519}"

ENGINES=("phi3-medium" "grok1" "mixtral" "allam")
TIERS=("base" "quantized" "adapters" "merged" "datasets" "eval" "manifests")

banner() {
  echo
  echo "=================================================================="
  echo "$1"
  echo "=================================================================="
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $1" >&2
    exit 1
  fi
}

install_prereqs() {
  banner "Installing vault prerequisites (rsync, openssh-server)"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y rsync openssh-server python3-pip
  else
    echo "ERROR: apt-get is required by this setup script." >&2
    exit 1
  fi

  if ! command -v huggingface-cli >/dev/null 2>&1; then
    banner "Installing huggingface-cli"
    python3 -m pip install --upgrade "huggingface_hub[cli]"
  fi
}

create_layout() {
  banner "Creating S3M Weight Vault directory structure at ${WEIGHTS_ROOT}"
  sudo mkdir -p "${WEIGHTS_ROOT}"
  sudo chown -R "$(id -u)":"$(id -g)" "${WEIGHTS_ROOT}"

  for tier in "${TIERS[@]}"; do
    mkdir -p "${WEIGHTS_ROOT}/${tier}"
    for engine in "${ENGINES[@]}"; do
      mkdir -p "${WEIGHTS_ROOT}/${tier}/${engine}"
    done
  done
  mkdir -p "${WEIGHTS_ROOT}/.keys"
}

setup_ssh_key() {
  banner "Generating SSH key pair for sync"
  if [[ -f "${KEY_PATH}" && -f "${KEY_PATH}.pub" ]]; then
    echo "SSH key already exists at ${KEY_PATH}; skipping."
    return
  fi

  ssh-keygen -t ed25519 -N "" -f "${KEY_PATH}"
  chmod 600 "${KEY_PATH}"
  chmod 644 "${KEY_PATH}.pub"
  echo "SSH key generated at ${KEY_PATH}"
}

configure_rsync() {
  banner "Configuring rsync daemon (/etc/rsyncd.conf)"
  local tmp_conf
  tmp_conf="$(mktemp)"

  cat >"${tmp_conf}" <<EOF
uid = root
gid = root
use chroot = no
max connections = 16
log file = /var/log/rsyncd.log
pid file = /var/run/rsyncd.pid
timeout = 600

[s3m-weights]
  path = ${WEIGHTS_ROOT}
  comment = S3M Weight Vault
  read only = false
  list = yes
EOF

  if [[ ! -f /etc/rsyncd.conf ]] || ! sudo cmp -s "${tmp_conf}" /etc/rsyncd.conf; then
    sudo cp "${tmp_conf}" /etc/rsyncd.conf
    echo "Updated /etc/rsyncd.conf"
  else
    echo "/etc/rsyncd.conf already up to date."
  fi

  rm -f "${tmp_conf}"

  if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable --now ssh || sudo systemctl enable --now sshd || true
    sudo systemctl enable --now rsync || sudo systemctl enable --now rsyncd || true
  fi
}

download_hf_repo() {
  local repo="$1"
  local dest="$2"
  shift 2

  mkdir -p "${dest}"
  if [[ -f "${dest}/.download_complete" ]]; then
    echo "Already complete: ${repo} -> ${dest}"
    return
  fi

  if [[ -n "$(ls -A "${dest}" 2>/dev/null)" ]]; then
    echo "Existing files detected in ${dest}; treating as already downloaded."
    touch "${dest}/.download_complete"
    return
  fi

  echo "Downloading ${repo} -> ${dest}"
  huggingface-cli download "${repo}" --resume-download --local-dir "${dest}" "$@"
  touch "${dest}/.download_complete"
}

download_weights() {
  banner "Pulling FULL fp16 base weights into vault"
  echo "NOTE: Ensure HF_TOKEN / hf auth is configured for gated repositories."
  download_hf_repo "microsoft/Phi-3-medium-4k-instruct" "${WEIGHTS_ROOT}/base/phi3-medium"
  download_hf_repo "xai-org/grok-1" "${WEIGHTS_ROOT}/base/grok1" --include "ckpt-0/*"
  download_hf_repo "mistralai/Mixtral-8x7B-Instruct-v0.1" "${WEIGHTS_ROOT}/base/mixtral"
  download_hf_repo "humain-ai/ALLaM-7B-Instruct-preview" "${WEIGHTS_ROOT}/base/allam"

  banner "Pulling pre-quantized GGUF artifacts where available"
  download_hf_repo "TheBloke/Mixtral-8x7B-Instruct-v0.1-GGUF" "${WEIGHTS_ROOT}/quantized/mixtral" --include "*.gguf"
  download_hf_repo "bartowski/Phi-3-medium-4k-instruct-GGUF" "${WEIGHTS_ROOT}/quantized/phi3-medium" --include "*.gguf"
}

print_summary() {
  banner "Vault disk utilization summary"
  du -sh "${WEIGHTS_ROOT}" || true
  df -h "${WEIGHTS_ROOT}" || true
  echo "Vault setup complete."
}

main() {
  require_cmd ssh-keygen
  install_prereqs
  require_cmd huggingface-cli
  create_layout
  setup_ssh_key
  configure_rsync
  download_weights
  print_summary
}

main "$@"
