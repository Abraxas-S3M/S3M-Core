"""Credential discovery and remediation for agent-accessible filesystems."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Iterable, List


@dataclass(frozen=True)
class CredentialFinding:
    """One credential match produced by regex or entropy analysis."""

    path: str
    line_number: int
    credential_type: str
    pattern_matched: str
    severity: str
    redacted_preview: str


@dataclass(frozen=True)
class ScrubReport:
    """Result summary for a scrub operation."""

    path: str
    mode: str
    total_findings: int
    files_modified: int
    files_removed: int
    redacted_entries: int


class CredentialScrubber:
    """
    Detect and neutralize credential exposure before model access.

    Tactical context:
    Credential denial blocks lateral movement opportunities and prevents
    an adversarial agent from escalating beyond the mission sandbox.
    """

    _PATTERNS = {
        "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "gcp_service_key": re.compile(r"\"type\"\s*:\s*\"service_account\""),
        "azure_connection_string": re.compile(r"DefaultEndpointsProtocol=.*;AccountKey=[^;]+;"),
        "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
        "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}"),
        "private_key_header": re.compile(r"-----BEGIN (RSA|EC|OPENSSH|ED25519) PRIVATE KEY-----"),
        "jwt_token": re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
        "bearer_token": re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{20,}"),
        "oauth_token": re.compile(r"oauth[_-]?token\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.=]{8,}"),
        "db_connection_string": re.compile(r"[a-z]+:\/\/[^:\s]+:[^@\s]+@[^\/\s]+\/[^\s]+", re.IGNORECASE),
        "dotenv_assignment": re.compile(
            r"^\s*(?:export\s+)?[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*.+$"
        ),
    }
    _SENSITIVE_FILES = {
        ".env",
        ".env.local",
        "id_rsa",
        "id_ed25519",
        "authorized_keys",
        "credentials",
        "kubeconfig",
        "config.json",
    }
    _ENV_SECRET_KEY = re.compile(
        r"(KEY|TOKEN|SECRET|PASSWORD|PASS|CREDENTIAL|AWS_|AZURE_|GCP_|OPENAI|ANTHROPIC|JWT|BEARER)",
        re.IGNORECASE,
    )

    def __init__(self, scan_paths: List[str]) -> None:
        if not scan_paths:
            raise ValueError("scan_paths must not be empty")
        self.scan_paths = [os.path.abspath(path) for path in scan_paths]
        self._watcher_thread: threading.Thread | None = None
        self._watcher_stop = threading.Event()

    def scan(self, path: str | None = None) -> List[CredentialFinding]:
        """Run regex + entropy scanning and return structured findings."""
        targets = self._resolve_targets(path)
        findings: list[CredentialFinding] = []

        for candidate in targets:
            if os.path.isfile(candidate):
                findings.extend(self._scan_file(candidate))
                continue
            for dir_path, _, file_names in os.walk(candidate):
                for file_name in file_names:
                    full = os.path.join(dir_path, file_name)
                    findings.extend(self._scan_file(full))
        return findings

    def scrub(self, path: str, mode: str = "redact") -> ScrubReport:
        """Scrub credentials by redacting, removing, or only reporting findings."""
        safe_mode = mode.strip().lower()
        if safe_mode not in {"redact", "remove", "report"}:
            raise ValueError("mode must be one of: redact, remove, report")

        findings = self.scan(path)
        file_to_findings: dict[str, list[CredentialFinding]] = {}
        for finding in findings:
            file_to_findings.setdefault(finding.path, []).append(finding)

        files_modified = 0
        files_removed = 0
        redacted_entries = 0

        if safe_mode == "remove":
            for target in file_to_findings:
                if os.path.isfile(target):
                    os.remove(target)
                    files_removed += 1
        elif safe_mode == "redact":
            for target, target_findings in file_to_findings.items():
                if not os.path.isfile(target):
                    continue
                content = self._read_text(target)
                if content is None:
                    continue
                redacted = content
                before = redacted
                for pattern in self._PATTERNS.values():
                    redacted, count = pattern.subn("[REDACTED]", redacted)
                    redacted_entries += count
                if redacted != before:
                    with open(target, "w", encoding="utf-8") as handle:
                        handle.write(redacted)
                    files_modified += 1
                else:
                    redacted_entries += len(target_findings)

        return ScrubReport(
            path=os.path.abspath(path),
            mode=safe_mode,
            total_findings=len(findings),
            files_modified=files_modified,
            files_removed=files_removed,
            redacted_entries=redacted_entries,
        )

    def scrub_environment(self) -> None:
        """Remove credential-like env vars and replace with D04 vault references."""
        replacements: dict[str, str] = {}
        for key in list(os.environ):
            if not self._ENV_SECRET_KEY.search(key):
                continue
            del os.environ[key]
            replacements[f"{key}_VAULT_REF"] = f"vault://d04/{key.lower()}"
        os.environ.update(replacements)

    def install_watcher(self) -> None:
        """Continuously re-scan for new files and scrub leaked credentials."""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher_thread.start()

    def stop_watcher(self) -> None:
        """Stop the background watcher thread."""
        self._watcher_stop.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=2.0)

    def _watch_loop(self) -> None:
        seen: set[str] = set()
        while not self._watcher_stop.is_set():
            for target in self._resolve_targets(None):
                if os.path.isfile(target):
                    candidates = [target]
                else:
                    candidates = []
                    for dir_path, _, file_names in os.walk(target):
                        for file_name in file_names:
                            candidates.append(os.path.join(dir_path, file_name))
                for candidate in candidates:
                    if candidate in seen:
                        continue
                    seen.add(candidate)
                    report = self.scrub(candidate, mode="redact")
                    if report.total_findings > 0:
                        # Auto-redaction is intentional to deny immediate secret exfiltration.
                        pass
            time.sleep(1.0)

    def _scan_file(self, path: str) -> list[CredentialFinding]:
        findings: list[CredentialFinding] = []
        file_name = os.path.basename(path)
        if file_name in self._SENSITIVE_FILES or any(marker in path for marker in (".aws/credentials", ".kube/config")):
            findings.append(
                CredentialFinding(
                    path=path,
                    line_number=0,
                    credential_type="sensitive_file",
                    pattern_matched=file_name,
                    severity="critical",
                    redacted_preview=f"{file_name}: [REDACTED]",
                )
            )

        lines = self._read_lines(path)
        if lines is None:
            return findings

        for index, line in enumerate(lines, start=1):
            for cred_type, pattern in self._PATTERNS.items():
                match = pattern.search(line)
                if not match:
                    continue
                findings.append(
                    CredentialFinding(
                        path=path,
                        line_number=index,
                        credential_type=cred_type,
                        pattern_matched=pattern.pattern,
                        severity=self._severity_for_type(cred_type),
                        redacted_preview=self._redact_line(line, match.group(0)),
                    )
                )
            for token in self._entropy_candidates(line):
                if self._shannon_entropy(token) >= 4.2:
                    findings.append(
                        CredentialFinding(
                            path=path,
                            line_number=index,
                            credential_type="high_entropy_secret",
                            pattern_matched="[entropy>=4.2]",
                            severity="suspicious",
                            redacted_preview=self._redact_line(line, token),
                        )
                    )
        return findings

    def _resolve_targets(self, path: str | None) -> list[str]:
        if path is None:
            return [target for target in self.scan_paths if os.path.exists(target)]
        safe_path = os.path.abspath(path)
        if not os.path.exists(safe_path):
            return []
        return [safe_path]

    @staticmethod
    def _read_lines(path: str) -> list[str] | None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.readlines()
        except OSError:
            return None

    @staticmethod
    def _read_text(path: str) -> str | None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None

    @staticmethod
    def _entropy_candidates(line: str) -> Iterable[str]:
        return re.findall(r"[A-Za-z0-9_\-+/=]{20,}", line)

    @staticmethod
    def _shannon_entropy(value: str) -> float:
        if not value:
            return 0.0
        frequency = {char: value.count(char) for char in set(value)}
        length = len(value)
        return -sum((count / length) * math.log2(count / length) for count in frequency.values())

    @staticmethod
    def _redact_line(line: str, secret: str) -> str:
        return line.replace(secret, "[REDACTED]").strip()

    @staticmethod
    def _severity_for_type(credential_type: str) -> str:
        if credential_type in {"private_key_header", "aws_access_key", "openai_key", "anthropic_key"}:
            return "critical"
        return "suspicious"
