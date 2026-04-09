#!/usr/bin/env bash
# Military/tactical context:
# This cron-compatible wrapper enforces recurring adapter quality checks so
# degraded outputs do not propagate into operational sync cycles.
#
# Example crontab entry (every 2 hours):
# 0 */2 * * * /workspace/scripts/training/run_grok_validation_cron.sh >> /workspace/logs/grok_validation_cron.log 2>&1

set -euo pipefail

REPO_ROOT="/workspace"
MODE="${GROK_ORACLE_MODE:-offline}"
TRACK_ARG=""
XAI_ARG=""

if [[ -n "${GROK_ORACLE_TRACK:-}" ]]; then
  TRACK_ARG="--track ${GROK_ORACLE_TRACK}"
fi

if [[ "${MODE}" == "api" ]]; then
  if [[ -z "${XAI_API_KEY:-}" ]]; then
    echo "XAI_API_KEY is required when GROK_ORACLE_MODE=api" >&2
    exit 2
  fi
  XAI_ARG="--xai-key ${XAI_API_KEY}"
fi

cd "${REPO_ROOT}"
python3 scripts/training/run_grok_validation.py --mode "${MODE}" ${TRACK_ARG} ${XAI_ARG}
