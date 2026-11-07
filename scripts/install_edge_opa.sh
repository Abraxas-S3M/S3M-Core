#!/usr/bin/env bash
# Install pinned OPA binary for offline Jetson / air-gapped policy gates.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPA_VERSION="${OPA_VERSION:-0.70.0}"
ARCH="${ARCH:-amd64}"
DEST="${ROOT}/tools/bin/opa"

mkdir -p "$(dirname "${DEST}")"
curl -fsSL -o "${DEST}" "https://openpolicyagent.org/downloads/v${OPA_VERSION}/opa_linux_${ARCH}_static"
chmod +x "${DEST}"
"${DEST}" version
