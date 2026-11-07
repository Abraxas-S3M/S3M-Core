#!/bin/bash
# Merge customer Cortex exclusions into the repo-root .dockerignore for docker build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
{
  if [ -f docker/.dockerignore ]; then
    cat docker/.dockerignore
  fi
  echo "# cortex customer profile"
  cat docker/cortex/customer.dockerignore
} > .dockerignore
echo "Wrote merged .dockerignore for customer Cortex build."
