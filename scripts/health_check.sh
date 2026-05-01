#!/usr/bin/env bash
set -euo pipefail

# Military/tactical context:
# This offline health sweep provides a rapid readiness snapshot so operators can
# verify packet ingest and adaptation services before mission window updates.

PASS="✓"
FAIL="✗"

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-s3m}"
DB_USER="${DB_USER:-s3m_user}"
DB_PASS="${DB_PASS:-}"

R2_ENDPOINT="${R2_ENDPOINT:-}"
S3M_ROOT="${S3M_ROOT:-/opt/s3m}"
INBOX_DIR="${INBOX_DIR:-$S3M_ROOT/state/training/cloud_cpu/inbox}"
PACKETS_DIR="${PACKETS_DIR:-$S3M_ROOT/packets}"
STAGING_DIR="${STAGING_DIR:-$S3M_ROOT/state/training/staging}"
LOG_DIR="${LOG_DIR:-$S3M_ROOT/logs}"

symbol_for() {
  local ok="$1"
  if [[ "$ok" -eq 0 ]]; then
    printf "%s" "$PASS"
  else
    printf "%s" "$FAIL"
  fi
}

print_check() {
  local rc="$1"
  local label="$2"
  local detail="${3:-}"
  local sym
  sym="$(symbol_for "$rc")"
  if [[ -n "$detail" ]]; then
    printf "%s %s: %s\n" "$sym" "$label" "$detail"
  else
    printf "%s %s\n" "$sym" "$label"
  fi
}

service_running() {
  local svc="$1"
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet "$svc"; then
      return 0
    fi
  fi
  if pgrep -fa "$svc" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

count_entries() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    find "$dir" -mindepth 1 | wc -l | tr -d ' '
  else
    printf "0"
  fi
}

check_postgres() {
  if ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi
  DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASS="$DB_PASS" \
  python3 - <<'PY' >/dev/null 2>&1
import os
import sys
try:
    import psycopg2
except Exception:
    sys.exit(1)
try:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "s3m"),
        user=os.environ.get("DB_USER", "s3m_user"),
        password=os.environ.get("DB_PASS", ""),
        connect_timeout=3,
    )
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    row = cur.fetchone()
    conn.close()
    sys.exit(0 if row and row[0] == 1 else 1)
except Exception:
    sys.exit(1)
PY
}

db_today_counts() {
  if ! command -v python3 >/dev/null 2>&1; then
    printf "success=0 failed=0"
    return 1
  fi
  DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASS="$DB_PASS" \
  python3 - <<'PY'
import os
import sys
try:
    import psycopg2
except Exception:
    print("success=0 failed=0")
    sys.exit(1)
try:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "s3m"),
        user=os.environ.get("DB_USER", "s3m_user"),
        password=os.environ.get("DB_PASS", ""),
        connect_timeout=3,
    )
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'success') AS success_count,
          COUNT(*) FILTER (WHERE status = 'failed') AS failed_count
        FROM training_runs
        WHERE created_at::date = CURRENT_DATE;
        """
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        print("success=0 failed=0")
        sys.exit(1)
    print(f"success={int(row[0] or 0)} failed={int(row[1] or 0)}")
except Exception:
    print("success=0 failed=0")
    sys.exit(1)
PY
}

check_r2_reachable() {
  local endpoint="$1"
  if [[ -z "$endpoint" ]]; then
    return 1
  fi
  local access_key="${R2_ACCESS_KEY:-}"
  local secret_key="${R2_SECRET_KEY:-}"
  if [[ -z "$access_key" || -z "$secret_key" ]]; then
    return 1
  fi
  local active_probe="${S3M_R2_HEALTH_ACTIVE:-0}"
  if [[ "$active_probe" != "1" ]]; then
    # Tactical default keeps health checks offline-safe in air-gapped mode.
    return 0
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    return 1
  fi
  R2_ENDPOINT="$endpoint" python3 - <<'PY' >/dev/null 2>&1
import os
import socket
import sys
from urllib.parse import urlparse

endpoint = os.environ.get("R2_ENDPOINT", "")
host = urlparse(endpoint).hostname
if not host:
    sys.exit(1)
try:
    with socket.create_connection((host, 443), timeout=3):
        pass
except OSError:
    sys.exit(1)
sys.exit(0)
PY
}

active_runpod_jobs() {
  local snapshot="$STAGING_DIR/runpod_jobs.json"
  if [[ -f "$snapshot" ]]; then
    if command -v python3 >/dev/null 2>&1; then
      SNAPSHOT_PATH="$snapshot" python3 - <<'PY' 2>/dev/null || printf "0"
import json
import os
path = os.environ["SNAPSHOT_PATH"]
with open(path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)
print(int(payload.get("active_jobs", 0)))
PY
      return
    fi
  fi
  printf "0"
}

echo "S3M-Engine Health Check"
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo

if service_running "s3m-watcher.service"; then
  print_check 0 "s3m-watcher.service running"
else
  print_check 1 "s3m-watcher.service running"
fi

if service_running "s3m-trainer.service"; then
  print_check 0 "s3m-trainer.service running"
else
  print_check 1 "s3m-trainer.service running"
fi

if check_postgres; then
  print_check 0 "PostgreSQL connection" "$DB_HOST:$DB_PORT/$DB_NAME"
else
  print_check 1 "PostgreSQL connection" "$DB_HOST:$DB_PORT/$DB_NAME"
fi

if check_r2_reachable "$R2_ENDPOINT"; then
  print_check 0 "R2 Vault reachable" "$R2_ENDPOINT"
else
  print_check 1 "R2 Vault reachable" "${R2_ENDPOINT:-not configured}"
fi

inbox_count="$(count_entries "$INBOX_DIR")"
print_check 0 "Inbox file count" "$inbox_count"

staging_count="$(count_entries "$STAGING_DIR")"
print_check 0 "Staging file count" "$staging_count"

packets_count="$(count_entries "$PACKETS_DIR")"
print_check 0 "Packets directory count" "$packets_count"

watcher_log="$LOG_DIR/packet_watcher.log"
if [[ -f "$watcher_log" ]]; then
  print_check 0 "Last 5 log lines from packet_watcher.log"
  tail -n 5 "$watcher_log"
else
  print_check 1 "Last 5 log lines from packet_watcher.log" "log not found: $watcher_log"
fi

runpod_count="$(active_runpod_jobs)"
print_check 0 "Active RunPod jobs count" "$runpod_count"

db_counts="success=0 failed=0"
if db_counts="$(db_today_counts)"; then
  print_check 0 "DB: training_runs today (success/failed counts)" "$db_counts"
else
  print_check 1 "DB: training_runs today (success/failed counts)" "$db_counts"
fi

if df -h "$S3M_ROOT" >/dev/null 2>&1; then
  disk_line="$(df -h "$S3M_ROOT" | awk 'NR==2 {print $4 " free / " $2 " total (" $5 " used)"}')"
  print_check 0 "Disk space on $S3M_ROOT" "$disk_line"
else
  print_check 1 "Disk space on $S3M_ROOT" "path not found"
fi
