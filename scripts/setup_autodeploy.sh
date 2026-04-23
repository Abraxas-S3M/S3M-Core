#!/usr/bin/env bash
# Provision an authenticated webhook listener for tactical software refresh.

set -euo pipefail

REPO_PATH="/opt/s3m"
ENV_FILE="${REPO_PATH}/.env.deploy"
SERVICE_FILE="/etc/systemd/system/s3m-autodeploy.service"
PYTHON_BIN="/usr/bin/python3"
LISTENER_SCRIPT="${REPO_PATH}/scripts/auto_deploy.py"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This setup script must run as root (use sudo)." >&2
  exit 1
fi

if [[ ! -d "${REPO_PATH}" ]]; then
  echo "Repository path not found: ${REPO_PATH}" >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Missing Python executable: ${PYTHON_BIN}" >&2
  exit 1
fi

if ! command -v pip3 >/dev/null 2>&1; then
  echo "pip3 is required but was not found." >&2
  exit 1
fi

if [[ ! -f "${LISTENER_SCRIPT}" ]]; then
  echo "Webhook listener script not found: ${LISTENER_SCRIPT}" >&2
  exit 1
fi

mkdir -p "${REPO_PATH}/logs"

if ! "${PYTHON_BIN}" -c "import flask" >/dev/null 2>&1; then
  pip3 install flask
fi

WEBHOOK_SECRET="$("${PYTHON_BIN}" -c "import secrets; print(secrets.token_urlsafe(48))")"

cat > "${ENV_FILE}" <<EOF
S3M_WEBHOOK_SECRET=${WEBHOOK_SECRET}
EOF
chmod 600 "${ENV_FILE}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=S3M GitHub Auto-Deploy Webhook Listener
After=network.target

[Service]
Type=simple
WorkingDirectory=${REPO_PATH}
EnvironmentFile=${ENV_FILE}
ExecStart=${PYTHON_BIN} ${LISTENER_SCRIPT}
Restart=always
RestartSec=5
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable s3m-autodeploy.service
systemctl restart s3m-autodeploy.service

SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [[ -z "${SERVER_IP}" ]]; then
  SERVER_IP="138.199.171.135"
fi

echo ""
echo "S3M auto-deploy listener configured successfully."
echo "Webhook URL: http://${SERVER_IP}:9090/github-webhook"
echo "Webhook secret: ${WEBHOOK_SECRET}"
echo "GitHub event: push"
echo "Service status command: systemctl status s3m-autodeploy.service"
