#!/usr/bin/env bash
# Install TLC model checker jar for formal verification workflows.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TLA_VERSION="${TLA_VERSION:-v1.8.0}"
DEST="${ROOT}/tools/bin/tla2tools.jar"

mkdir -p "$(dirname "${DEST}")"
curl -fsSL -o "${DEST}" "https://github.com/tlaplus/tlaplus/releases/download/${TLA_VERSION}/tla2tools.jar"
ls -lh "${DEST}"
