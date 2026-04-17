"""Git history hardening and forensic diff annotation utilities."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
import subprocess
from typing import Any, List


@dataclass(frozen=True)
class HistoryReport:
    """Structured result from full-history integrity verification."""

    total_commits: int
    suspicious_commits: List[dict[str, Any]]
    history_intact: bool
    merkle_root: str


@dataclass(frozen=True)
class DiffReport:
    """Security-focused annotation output for a single commit diff."""

    commit_hash: str
    files_changed: List[str]
    credential_hits: List[dict[str, str]]
    permission_changes: List[str]
    new_executables: List[str]
    cicd_changes: List[str]


class GitGuardian:
    """
    Detect and deter repository-level tampering in contested environments.

    Tactical context:
    Threat actors often hide malicious edits by mutating history. Guardian
    checks preserve chain-of-custody so operators can trust audit evidence.
    """

    _EMPTY_OR_TEMPLATED_MESSAGES = {
        "",
        "update",
        "fix",
        "wip",
        "temp",
        "misc",
        "test",
        "changes",
    }
    _CREDENTIAL_PATTERNS = {
        "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
        "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"),
        "generic_token": re.compile(r"(token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/.+=]{8,}"),
        "jwt": re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    }
    _CICD_FILE_HINTS = (
        ".github/workflows/",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        "azure-pipelines.yml",
        "buildkite.yml",
        "circleci/config.yml",
    )

    def __init__(self, repo_paths: List[str]) -> None:
        if not repo_paths:
            raise ValueError("repo_paths must include at least one repository path")
        self.repo_paths = [os.path.abspath(path) for path in repo_paths]

    def install_hooks(self, repo_path: str) -> None:
        """Install pre-receive and post-receive hooks to block stealth tampering."""
        safe_repo = self._validate_repo_path(repo_path)
        hooks_dir = self._hook_dir(safe_repo)
        os.makedirs(hooks_dir, exist_ok=True)

        pre_receive = """#!/usr/bin/env bash
set -euo pipefail
AUDIT_LOG="$(git rev-parse --git-dir)/s3m_incoming_push_audit.log"
while read -r oldrev newrev refname; do
  if [[ "$oldrev" != "0000000000000000000000000000000000000000" ]]; then
    if ! git merge-base --is-ancestor "$oldrev" "$newrev"; then
      echo "S3M GitGuardian: force-push history rewrite rejected for $refname" >&2
      exit 1
    fi
  fi
  changed="$(git diff --name-only "$oldrev" "$newrev" || true)"
  if echo "$changed" | grep -E '(^|/)\\.git(ignore|attributes)$' >/dev/null 2>&1; then
    if git diff "$oldrev" "$newrev" -- .gitignore .gitattributes | grep -E '^\\+.*(evidence|audit|forensic|\\*|\\.log|\\.tmp)' >/dev/null 2>&1; then
      echo "S3M GitGuardian: suspicious ignore-rule mutation rejected." >&2
      exit 1
    fi
  fi
  for commit in $(git rev-list "$oldrev..$newrev"); do
    sig="$(git show -s --format=%G? "$commit")"
    if [[ "$sig" != "G" && "$sig" != "U" ]]; then
      echo "S3M GitGuardian: unsigned or untrusted commit $commit rejected." >&2
      exit 1
    fi
  done
  {
    echo "=== PUSH $(date -u +%Y-%m-%dT%H:%M:%SZ) ref=$refname old=$oldrev new=$newrev ==="
    git diff "$oldrev" "$newrev"
    echo
  } >> "$AUDIT_LOG"
done
"""

        post_receive = """#!/usr/bin/env bash
set -euo pipefail
GIT_DIR="$(git rev-parse --git-dir)"
MERKLE_LOG="$GIT_DIR/s3m_repo_merkle.log"
ALERT_LOG="$GIT_DIR/s3m_binary_alerts.log"
ROOT_HASH="$(git ls-tree -r HEAD | sha256sum | awk '{print $1}')"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $ROOT_HASH" >> "$MERKLE_LOG"
while read -r oldrev newrev refname; do
  binaries="$(git diff --numstat "$oldrev" "$newrev" | awk '$1=="-" || $2=="-" {print $3}')"
  if [[ -n "$binaries" ]]; then
    {
      echo "BINARY_CHANGE $(date -u +%Y-%m-%dT%H:%M:%SZ) ref=$refname old=$oldrev new=$newrev"
      echo "$binaries"
    } >> "$ALERT_LOG"
  fi
done
"""

        self._write_hook(os.path.join(hooks_dir, "pre-receive"), pre_receive)
        self._write_hook(os.path.join(hooks_dir, "post-receive"), post_receive)

    def verify_history(self, repo_path: str) -> HistoryReport:
        """Inspect commit history for concealment signals and chronology anomalies."""
        safe_repo = self._validate_repo_path(repo_path)
        output = self._git(
            safe_repo,
            ["log", "--all", "--date-order", "--reverse", "--format=%H%x1f%ct%x1f%P%x1f%s"],
        )
        commits = [line for line in output.splitlines() if line.strip()]
        suspicious: list[dict[str, Any]] = []
        commit_times: dict[str, int] = {}
        touched_paths: dict[str, set[str]] = {}

        for line in commits:
            commit_hash, timestamp, parent_blob, message = line.split("\x1f", 3)
            commit_time = int(timestamp)
            commit_times[commit_hash] = commit_time
            message_norm = message.strip().lower()
            parent_hashes = [parent for parent in parent_blob.split() if parent]

            names = self._git(safe_repo, ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash])
            changed_paths = {name.strip() for name in names.splitlines() if name.strip()}
            touched_paths[commit_hash] = changed_paths

            if any(path.startswith(".git/") for path in changed_paths):
                suspicious.append(
                    {"commit": commit_hash, "reason": "modifies .git internals directly", "severity": "critical"}
                )

            if message_norm in self._EMPTY_OR_TEMPLATED_MESSAGES or len(message_norm) < 4:
                suspicious.append(
                    {"commit": commit_hash, "reason": "empty or templated commit message", "severity": "suspicious"}
                )

            if parent_hashes:
                parent_times = [commit_times.get(parent) for parent in parent_hashes if parent in commit_times]
                if parent_times and commit_time + 12 * 3600 < max(parent_times):
                    suspicious.append(
                        {"commit": commit_hash, "reason": "unusual backdated timestamp", "severity": "suspicious"}
                    )

        for idx, line in enumerate(commits[:-1]):
            commit_hash = line.split("\x1f", 1)[0]
            next_hash = commits[idx + 1].split("\x1f", 1)[0]
            next_message = commits[idx + 1].split("\x1f", 3)[3].strip().lower()
            if "revert" in next_message and touched_paths.get(commit_hash, set()) & touched_paths.get(next_hash, set()):
                suspicious.append(
                    {
                        "commit": commit_hash,
                        "reason": "change immediately reverted in subsequent commit",
                        "severity": "suspicious",
                    }
                )

        reflog = self._git(safe_repo, ["reflog", "--all", "--format=%gs"], check=False)
        if any("forced-update" in line or "push (force" in line for line in reflog.splitlines()):
            suspicious.append(
                {"commit": "REFLOG", "reason": "force-push indicator found in reflog", "severity": "critical"}
            )

        merkle_root = self._repo_merkle_root(safe_repo, ref="HEAD")
        critical_count = sum(1 for item in suspicious if item["severity"] == "critical")
        history_intact = critical_count == 0
        return HistoryReport(
            total_commits=len(commits),
            suspicious_commits=suspicious,
            history_intact=history_intact,
            merkle_root=merkle_root,
        )

    def diff_audit(self, commit_hash: str) -> DiffReport:
        """Generate commit diff report with security annotations and pattern hits."""
        if not self.repo_paths:
            raise ValueError("No repository paths registered for diff audit")
        repo = self.repo_paths[0]
        safe_commit = commit_hash.strip()
        if not safe_commit:
            raise ValueError("commit_hash must be non-empty")

        files = self._git(repo, ["diff-tree", "--no-commit-id", "--name-only", "-r", safe_commit])
        files_changed = [line.strip() for line in files.splitlines() if line.strip()]
        patch = self._git(repo, ["show", "--format=", "--patch", safe_commit])
        summary = self._git(repo, ["show", "--summary", "--format=", safe_commit])

        credential_hits: list[dict[str, str]] = []
        current_file = ""
        for line in patch.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for label, pattern in self._CREDENTIAL_PATTERNS.items():
                match = pattern.search(line)
                if not match:
                    continue
                credential_hits.append(
                    {
                        "file": current_file,
                        "pattern": label,
                        "matched": self._redact(match.group(0)),
                    }
                )

        permission_changes = [
            line.strip()
            for line in summary.splitlines()
            if line.strip().startswith("old mode ") or line.strip().startswith("new mode ")
        ]
        new_executables = []
        for line in summary.splitlines():
            stripped = line.strip()
            if not stripped.startswith("create mode 100755"):
                continue
            parts = stripped.split()
            if parts:
                new_executables.append(parts[-1])
        cicd_changes = [
            path
            for path in files_changed
            if any(hint in path for hint in self._CICD_FILE_HINTS) or path.endswith((".yml", ".yaml"))
        ]

        return DiffReport(
            commit_hash=safe_commit,
            files_changed=files_changed,
            credential_hits=credential_hits,
            permission_changes=permission_changes,
            new_executables=new_executables,
            cicd_changes=cicd_changes,
        )

    def _validate_repo_path(self, repo_path: str) -> str:
        safe_repo = os.path.abspath(repo_path)
        git_dir = os.path.join(safe_repo, ".git")
        if os.path.isdir(git_dir):
            return safe_repo
        if os.path.isdir(os.path.join(safe_repo, "hooks")) and os.path.isfile(os.path.join(safe_repo, "HEAD")):
            return safe_repo
        raise ValueError(f"repo_path is not a git repository: {repo_path}")

    @staticmethod
    def _hook_dir(repo_path: str) -> str:
        git_dir = os.path.join(repo_path, ".git")
        if os.path.isdir(git_dir):
            return os.path.join(git_dir, "hooks")
        return os.path.join(repo_path, "hooks")

    @staticmethod
    def _write_hook(hook_path: str, body: str) -> None:
        with open(hook_path, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.chmod(hook_path, 0o755)

    @staticmethod
    def _redact(value: str) -> str:
        if len(value) <= 8:
            return "[REDACTED]"
        return f"{value[:4]}...[REDACTED]...{value[-4:]}"

    @staticmethod
    def _git(repo_path: str, args: list[str], check: bool = True) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if check and completed.returncode != 0:
            raise RuntimeError(
                f"git command failed ({' '.join(args)}): {completed.stderr.strip() or completed.stdout.strip()}"
            )
        return completed.stdout

    def _repo_merkle_root(self, repo_path: str, ref: str = "HEAD") -> str:
        listing = self._git(repo_path, ["ls-tree", "-r", ref, "--full-tree"])
        digest = hashlib.sha256()
        for line in sorted(filter(None, listing.splitlines())):
            digest.update(line.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()
