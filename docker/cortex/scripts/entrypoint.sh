#!/bin/sh
# Cortex tier entrypoint — supports read-only root via /tmp and /opt/s3m/run volumes.
set -eu

export PYTHONPATH="${PYTHONPATH:-/opt/s3m}"
export S3M_BUILD_PROFILE="${S3M_BUILD_PROFILE:-customer}"

case "${CORTEX_TIER:-core}" in
  core)
    exec python scripts/start_api.py "$@"
    ;;
  regional)
    exec python scripts/start_api.py "$@"
    ;;
  edge)
    exec python -m uvicorn src.edge_compute.edge_server:app \
      --host 0.0.0.0 --port 9090 --workers 1 --log-level "${S3M_LOG_LEVEL:-info}" "$@"
    ;;
  *)
    echo "Unknown CORTEX_TIER=${CORTEX_TIER}" >&2
    exit 2
    ;;
esac
