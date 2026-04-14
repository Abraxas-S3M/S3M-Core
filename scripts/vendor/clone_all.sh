#!/usr/bin/env bash
set -u

# S3M UNCLASSIFIED - FOUO
# Tactical context: this workflow stages third-party code into the sovereign
# vault with bounded local storage use so forward operators can recover
# dependencies even when internet paths are denied.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_REPOS_FILE="${SCRIPT_DIR}/repos.txt"
DEFAULT_LOG_FILE="/tmp/s3m-vendor-clone.log"
DEFAULT_TMP_ROOT="/tmp/s3m-vendor"

PARALLEL=1
DOMAIN_FILTER=""
DRY_RUN=0
REPOS_FILE="${DEFAULT_REPOS_FILE}"
LOG_FILE="${DEFAULT_LOG_FILE}"
WORKER_PAYLOAD=""
STATUS_FILE=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/vendor/clone_all.sh
  bash scripts/vendor/clone_all.sh --parallel 4
  bash scripts/vendor/clone_all.sh --domain cyber
  bash scripts/vendor/clone_all.sh --dry-run
Options:
  --parallel N     Process up to N repositories concurrently (default: 1)
  --domain DOMAIN  Restrict processing to one integration domain
  --dry-run        Print what would be processed without cloning/uploading
  --repos FILE     Override repos manifest path (default: scripts/vendor/repos.txt)
  --worker PAYLOAD Internal worker mode for xargs
EOF
}

timestamp_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

log_line() {
  local message="$1"
  printf '%s %s\n' "$(timestamp_utc)" "${message}" | tee -a "${LOG_FILE}"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    log_line "[FATAL] Missing command: ${cmd}"
    exit 2
  fi
}

require_env() {
  local key="$1"
  if [[ -z "${!key:-}" ]]; then
    log_line "[FATAL] Missing required environment variable: ${key}"
    exit 2
  fi
}

check_tmp_space() {
  local available_kb
  available_kb="$(df -Pk /tmp | awk 'NR==2 {print $4}')"
  if [[ -z "${available_kb}" ]]; then
    log_line "[FATAL] Unable to determine /tmp free space"
    exit 2
  fi
  if (( available_kb < 5 * 1024 * 1024 )); then
    log_line "[FATAL] /tmp has less than 5 GB free"
    exit 2
  fi
}

python_import_check() {
  python3 - "${REPO_ROOT}" <<'PY'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.storage.object_storage import ObjectStorageConnector  # noqa: F401
print("import-ok")
PY
}

object_storage_connection_check() {
  python3 - "${REPO_ROOT}" <<'PY'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.storage.object_storage import ObjectStorageConnector

connector = ObjectStorageConnector()
connector.list_keys("vendor/")
print("object-storage-ok")
PY
}

marker_exists() {
  local marker_key="$1"
  python3 - "${REPO_ROOT}" "${marker_key}" <<'PY'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
marker = str(sys.argv[2])
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.storage.object_storage import ObjectStorageConnector

try:
    exists = ObjectStorageConnector().file_exists(marker)
except Exception:
    raise
sys.exit(0 if exists else 1)
PY
}

upload_directory() {
  local local_dir="$1"
  local remote_prefix="$2"
  python3 - "${REPO_ROOT}" "${local_dir}" "${remote_prefix}" <<'PY'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
local_dir = Path(sys.argv[2]).resolve()
remote_prefix = str(sys.argv[3])
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.storage.object_storage import ObjectStorageConnector

ObjectStorageConnector().sync_up(local_dir, remote_prefix)
print("sync-up-ok")
PY
}

upload_marker() {
  local marker_file="$1"
  local remote_key="$2"
  python3 - "${REPO_ROOT}" "${marker_file}" "${remote_key}" <<'PY'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
marker_file = Path(sys.argv[2]).resolve()
remote_key = str(sys.argv[3])
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.storage.object_storage import ObjectStorageConnector

ObjectStorageConnector().upload_file(marker_file, remote_key)
print("marker-ok")
PY
}

calc_repo_stats() {
  local repo_path="$1"
  python3 - "${repo_path}" <<'PY'
import os
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
size_bytes = 0
file_count = 0
for current_root, _, files in os.walk(root):
    for name in files:
        file_path = Path(current_root) / name
        size_bytes += file_path.stat().st_size
        file_count += 1
print(f"{size_bytes}|{file_count}")
PY
}

format_size() {
  local bytes="$1"
  python3 - "${bytes}" <<'PY'
import sys

size = float(sys.argv[1])
units = ["B", "KB", "MB", "GB", "TB"]
for unit in units:
    if size < 1024.0 or unit == units[-1]:
        if unit == "B":
            print(f"{int(size)} {unit}")
        else:
            print(f"{size:.2f} {unit}")
        break
    size /= 1024.0
PY
}

clone_with_retries() {
  local url="$1"
  local dest="$2"
  local stderr_file="$3"
  local attempt
  for attempt in 1 2 3; do
    if git clone --depth 1 "${url}" "${dest}" 2>"${stderr_file}"; then
      return 0
    fi
    if [[ "${attempt}" -lt 3 ]]; then
      sleep $((2 ** attempt))
    fi
    rm -rf "${dest}"
  done
  return 1
}

write_status() {
  local status="$1"
  local bytes="$2"
  if [[ -n "${STATUS_FILE}" ]]; then
    printf '%s|%s\n' "${status}" "${bytes}" >>"${STATUS_FILE}"
  fi
}

process_one() {
  local index="$1"
  local total="$2"
  local domain="$3"
  local slug="$4"
  local url="$5"

  local remote_prefix="vendor/${domain}/${slug}/"
  local marker_key="${remote_prefix}.cloned"
  local temp_root="${DEFAULT_TMP_ROOT}/${domain}"
  local local_repo="${temp_root}/${slug}"
  local clone_stderr="/tmp/s3m-vendor-clone-${domain}-${slug}-stderr.log"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[${index}/${total}] ${domain}/${slug} (dry-run)"
    if marker_exists "${marker_key}" >/dev/null 2>&1; then
      log_line "[SKIP] ${domain}/${slug} marker exists (dry-run)"
      write_status "SKIP" "0"
    else
      log_line "[CLONE] ${domain}/${slug} would clone from ${url} (dry-run)"
      write_status "SUCCESS" "0"
    fi
    return 0
  fi

  if marker_exists "${marker_key}" >/dev/null 2>&1; then
    echo "[${index}/${total}] ${domain}/${slug} (skipped)"
    log_line "[SKIP] ${domain}/${slug} marker exists in object storage"
    write_status "SKIP" "0"
    return 0
  fi

  mkdir -p "${temp_root}"
  rm -rf "${local_repo}"

  log_line "[CLONE] ${domain}/${slug} ${url}"
  if ! clone_with_retries "${url}" "${local_repo}" "${clone_stderr}"; then
    local stderr_preview
    stderr_preview="$(tr '\n' ' ' <"${clone_stderr}" | sed 's/[[:space:]]\+/ /g')"
    if [[ "${stderr_preview,,}" == *"repository not found"* ]] || [[ "${stderr_preview,,}" == *"not found"* ]]; then
      log_line "[SKIP] ${domain}/${slug} repository not found (404): ${url}"
      rm -rf "${local_repo}" "${clone_stderr}"
      write_status "SKIP" "0"
      return 0
    fi
    log_line "[FAIL] ${domain}/${slug} clone failed: ${stderr_preview}"
    rm -rf "${local_repo}" "${clone_stderr}"
    write_status "FAIL" "0"
    return 1
  fi

  local commit_hash
  commit_hash="$(git -C "${local_repo}" rev-parse HEAD 2>/dev/null || echo "unknown")"
  rm -rf "${local_repo}/.git"

  local stats
  stats="$(calc_repo_stats "${local_repo}")"
  local size_bytes="${stats%%|*}"
  local file_count="${stats##*|}"
  local human_size
  human_size="$(format_size "${size_bytes}")"
  echo "[${index}/${total}] ${domain}/${slug} (${human_size})"

  if ! upload_directory "${local_repo}" "${remote_prefix}" >/dev/null 2>&1; then
    log_line "[FAIL] ${domain}/${slug} upload failed"
    rm -rf "${local_repo}" "${clone_stderr}"
    write_status "FAIL" "0"
    return 1
  fi

  local marker_file
  marker_file="$(mktemp /tmp/s3m-vendor-marker-XXXXXX)"
  {
    printf 'timestamp=%s\n' "$(timestamp_utc)"
    printf 'commit_hash=%s\n' "${commit_hash}"
    printf 'size_bytes=%s\n' "${size_bytes}"
    printf 'file_count=%s\n' "${file_count}"
  } >"${marker_file}"

  if ! upload_marker "${marker_file}" "${marker_key}" >/dev/null 2>&1; then
    log_line "[FAIL] ${domain}/${slug} marker upload failed"
    rm -f "${marker_file}" "${clone_stderr}"
    rm -rf "${local_repo}"
    write_status "FAIL" "0"
    return 1
  fi

  rm -f "${marker_file}" "${clone_stderr}"
  rm -rf "${local_repo}"
  log_line "[CLONE] ${domain}/${slug} uploaded (${human_size}, ${file_count} files)"
  write_status "SUCCESS" "${size_bytes}"
  return 0
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --parallel)
        PARALLEL="${2:-}"
        shift 2
        ;;
      --domain)
        DOMAIN_FILTER="${2:-}"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --repos)
        REPOS_FILE="${2:-}"
        shift 2
        ;;
      --worker)
        WORKER_PAYLOAD="${2:-}"
        shift 2
        ;;
      --status-file)
        STATUS_FILE="${2:-}"
        shift 2
        ;;
      --log-file)
        LOG_FILE="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage
        exit 2
        ;;
    esac
  done

  if ! [[ "${PARALLEL}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --parallel must be an integer >= 1" >&2
    exit 2
  fi
}

build_task_list() {
  local repos_file="$1"
  local domain_filter="$2"
  local output_file="$3"
  python3 - "${repos_file}" "${domain_filter}" "${output_file}" <<'PY'
import sys
from pathlib import Path

repos_file = Path(sys.argv[1]).resolve()
domain_filter = str(sys.argv[2]).strip()
output_file = Path(sys.argv[3]).resolve()

if not repos_file.exists():
    raise SystemExit("missing repos file")

raw_entries: list[tuple[str, str, str]] = []
for line in repos_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split("|")
    if len(parts) < 3:
        continue
    domain, slug, url = parts[0].strip(), parts[1].strip(), parts[2].strip()
    if domain_filter and domain != domain_filter:
        continue
    raw_entries.append((domain, slug, url))

total = len(raw_entries)
lines = [f"{idx}|{total}|{domain}|{slug}|{url}" for idx, (domain, slug, url) in enumerate(raw_entries, start=1)]
output_file.parent.mkdir(parents=True, exist_ok=True)
output_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
print(total)
PY
}

run_worker_payload() {
  local payload="$1"
  IFS='|' read -r index total domain slug url <<<"${payload}"
  process_one "${index}" "${total}" "${domain}" "${slug}" "${url}"
}

main() {
  parse_args "$@"
  cd "${REPO_ROOT}" || exit 2

  if [[ -n "${WORKER_PAYLOAD}" ]]; then
    run_worker_payload "${WORKER_PAYLOAD}"
    return $?
  fi

  : >"${LOG_FILE}"
  log_line "Start vendor clone run"
  log_line "Repos file: ${REPOS_FILE}"
  log_line "Domain filter: ${DOMAIN_FILTER:-<all>}"
  log_line "Parallel workers: ${PARALLEL}"
  log_line "Dry run: ${DRY_RUN}"

  require_cmd git
  require_cmd python3
  require_env S3M_STORAGE_ACCESS_KEY
  require_env S3M_STORAGE_SECRET_KEY
  require_env S3M_STORAGE_BUCKET_NAME
  require_env S3M_STORAGE_ENDPOINT
  check_tmp_space

  if [[ ! -s "${REPOS_FILE}" ]]; then
    log_line "[FATAL] repos.txt missing or empty: ${REPOS_FILE}"
    return 2
  fi

  if ! python_import_check >/dev/null 2>&1; then
    log_line "[FATAL] Cannot import src.storage.object_storage"
    return 2
  fi

  if ! object_storage_connection_check >/dev/null 2>&1; then
    log_line "[FATAL] Cannot connect to Cloudflare R2"
    return 2
  fi

  local task_file
  task_file="$(mktemp /tmp/s3m-vendor-tasks-XXXXXX.txt)"
  local total
  if ! total="$(build_task_list "${REPOS_FILE}" "${DOMAIN_FILTER}" "${task_file}")"; then
    log_line "[FATAL] Failed to parse repos file"
    rm -f "${task_file}"
    return 2
  fi

  if [[ "${total}" -eq 0 ]]; then
    log_line "[INFO] No repositories matched filters"
    rm -f "${task_file}"
    log_line "End vendor clone run: total=0 success=0 skip=0 fail=0 bytes=0"
    return 0
  fi

  local status_file
  status_file="$(mktemp /tmp/s3m-vendor-status-XXXXXX.txt)"
  STATUS_FILE="${status_file}"

  if [[ "${PARALLEL}" -lt 1 ]]; then
    log_line "[FATAL] --parallel must be >= 1"
    rm -f "${task_file}" "${status_file}"
    return 2
  fi

  if [[ "${PARALLEL}" -eq 1 ]]; then
    set +e
    while IFS= read -r payload; do
      [[ -z "${payload}" ]] && continue
      IFS='|' read -r index total_rows domain slug url <<<"${payload}"
      process_one "${index}" "${total_rows}" "${domain}" "${slug}" "${url}"
    done <"${task_file}"
    set -e
  else
    local worker_extra=""
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      worker_extra="--dry-run"
    fi
    xargs -P "${PARALLEL}" -I{} bash "${BASH_SOURCE[0]}" --worker "{}" --status-file "${status_file}" --log-file "${LOG_FILE}" ${worker_extra} <"${task_file}" || true
  fi

  local success_count
  local skip_count
  local fail_count
  local total_bytes
  success_count="$(awk -F'|' '$1=="SUCCESS"{count+=1} END{print count+0}' "${status_file}")"
  skip_count="$(awk -F'|' '$1=="SKIP"{count+=1} END{print count+0}' "${status_file}")"
  fail_count="$(awk -F'|' '$1=="FAIL"{count+=1} END{print count+0}' "${status_file}")"
  total_bytes="$(awk -F'|' '{sum+=$2} END{print sum+0}' "${status_file}")"

  log_line "End vendor clone run: total=${total} success=${success_count} skip=${skip_count} fail=${fail_count} bytes=${total_bytes}"
  rm -f "${task_file}" "${status_file}"

  if [[ "${fail_count}" -gt 0 ]]; then
    return 1
  fi
  return 0
}

main "$@"
