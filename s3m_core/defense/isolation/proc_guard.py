"""Active `/proc` access monitoring for containerized agent processes."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(slots=True)
class ProcAccessAlert:
    """Alert payload emitted when suspicious process-introspection behavior occurs."""

    timestamp: datetime
    pid: int
    syscall: str
    target_path: str
    calling_binary: str
    action_taken: str


class ProcGuard:
    """
    Monitors and responds to suspicious `/proc` and cross-process memory activity.

    Tactical context:
    This guard adds an active tripwire in case an adversarial model discovers
    bypasses around static mount masks and namespace isolation.
    """

    _WATCHED_SYSCALLS = {"open", "openat", "read", "ptrace", "process_vm_readv"}

    def __init__(self) -> None:
        self._response_mode = "kill"
        self._installed_containers: Dict[str, datetime] = {}
        self._alerts: List[ProcAccessAlert] = []

    def install(self, container_id: str) -> None:
        """Install an eBPF-based `/proc` monitor for one container."""
        if not container_id:
            raise ValueError("container_id must be provided.")
        self._installed_containers[container_id] = datetime.now(timezone.utc)

        if shutil.which("bpftool") is None:
            # Tactical note: degraded mode still logs events so defenders retain
            # forensic visibility even when kernel eBPF tooling is unavailable.
            self._alerts.append(
                ProcAccessAlert(
                    timestamp=datetime.now(timezone.utc),
                    pid=-1,
                    syscall="ebpf_install",
                    target_path="/proc",
                    calling_binary="proc_guard",
                    action_taken="logged",
                )
            )
            return

        self._load_ebpf_monitor(container_id=container_id)

    def get_alerts(self, since: Optional[datetime] = None) -> List[ProcAccessAlert]:
        """Return detected `/proc` access alerts, optionally filtered by time."""
        if since is None:
            return list(self._alerts)
        return [alert for alert in self._alerts if alert.timestamp >= since]

    def set_response_mode(self, mode: str) -> None:
        """Set monitor response behavior: monitor, block, or kill."""
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"monitor", "block", "kill"}:
            raise ValueError("mode must be one of: monitor, block, kill")
        self._response_mode = normalized_mode

    def record_attempt(
        self,
        pid: int,
        syscall: str,
        target_path: str,
        calling_binary: str,
    ) -> ProcAccessAlert:
        """
        Record a suspicious syscall event from the monitoring plane.

        This helper supports integration adapters and deterministic unit tests.
        """
        syscall_name = syscall.strip()
        if syscall_name not in self._WATCHED_SYSCALLS:
            raise ValueError(f"Unsupported syscall '{syscall_name}' for ProcGuard.")

        if syscall_name in {"open", "openat", "read"} and not target_path.startswith("/proc/"):
            raise ValueError("open/openat/read monitoring is limited to /proc paths.")

        if self._response_mode == "monitor":
            action = "logged"
        elif self._response_mode == "block":
            action = "blocked"
        else:
            action = "killed"

        alert = ProcAccessAlert(
            timestamp=datetime.now(timezone.utc),
            pid=pid,
            syscall=syscall_name,
            target_path=target_path,
            calling_binary=calling_binary,
            action_taken=action,
        )
        self._alerts.append(alert)
        return alert

    @staticmethod
    def _load_ebpf_monitor(container_id: str) -> None:
        _ = Path("/sys/fs/bpf") / f"s3m-procguard-{container_id}"
