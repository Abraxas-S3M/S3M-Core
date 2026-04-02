#!/bin/bash
# File: docker/entrypoint-edge.sh
# S3M Edge Node Entrypoint - starts the edge API and watches for config changes
# UNCLASSIFIED - FOUO

set -e

echo "==============================================="
echo "  S3M Edge Node Starting"
echo "  Node ID: ${S3M_NODE_ID:-auto}"
echo "  Config:  ${S3M_CONFIG_PATH}"
echo "==============================================="

# Start config watcher in background (reloads on params.json change)
if command -v inotifywait &> /dev/null && [ -f "${S3M_CONFIG_PATH}" ]; then
    (
        while true; do
            inotifywait -e modify "${S3M_CONFIG_PATH}" 2>/dev/null
            echo "[config-watcher] params.json changed, signaling reload"
            # Send SIGHUP to the Python process to trigger config reload
            pkill -HUP -f "uvicorn" 2>/dev/null || true
        done
    ) &
    echo "[entrypoint] Config watcher started for ${S3M_CONFIG_PATH}"
fi

# Start the edge API server
exec python -m uvicorn src.edge_compute.edge_server:app \
    --host 0.0.0.0 \
    --port 9090 \
    --workers 1 \
    --log-level "${S3M_LOG_LEVEL:-info}"
