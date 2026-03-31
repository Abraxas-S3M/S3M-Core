"""Air-gap verification checks for S3M tactical deployments."""

from __future__ import annotations

import os
import platform
import socket
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional


class AirGapVerifier:
    """Validate that the runtime environment remains network-isolated."""

    def __init__(
        self,
        allowed_interfaces: Optional[List[str]] = None,
        check_interval_seconds: float = 300.0,
        allowed_extra_ports: Optional[List[int]] = None,
    ) -> None:
        self.allowed_interfaces = allowed_interfaces or ["lo", "docker0"]
        self.check_interval_seconds = float(check_interval_seconds)
        self.allowed_extra_ports = allowed_extra_ports or []
        self._last_result: Optional[Dict[str, object]] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_allowed_ports(self) -> List[int]:
        """Return default allowed API port plus configured extras."""
        merged = {8080, *self.allowed_extra_ports}
        return sorted(int(p) for p in merged)

    def verify(self) -> Dict[str, object]:
        """Run full air-gap checks and return machine-readable results."""
        if platform.system().lower() != "linux":
            result = {
                "air_gapped": None,
                "note": "Cannot verify on non-Linux — checks skipped",
                "timestamp": self._ts(),
                "violations": [],
                "checks_performed": [],
            }
            self._last_result = result
            return result

        violations: List[Dict[str, object]] = []
        checks_performed: List[str] = []

        # Check 1: interfaces
        try:
            checks_performed.append("network_interfaces")
            self._check_interfaces(violations)
        except Exception as exc:  # pragma: no cover - defensive
            violations.append(
                {
                    "check": "network_interfaces",
                    "severity": "WARN",
                    "detail": f"check inconclusive: {exc}",
                }
            )

        # Check 2: DNS resolution should fail in air-gapped deployment.
        try:
            checks_performed.append("dns_resolution")
            self._check_dns(violations)
        except Exception as exc:  # pragma: no cover - defensive
            violations.append(
                {
                    "check": "dns_resolution",
                    "severity": "WARN",
                    "detail": f"check inconclusive: {exc}",
                }
            )

        # Check 3: outbound connectivity should fail.
        try:
            checks_performed.append("outbound_connectivity")
            self._check_outbound_connectivity(violations)
        except Exception as exc:  # pragma: no cover - defensive
            violations.append(
                {
                    "check": "outbound_connectivity",
                    "severity": "WARN",
                    "detail": f"check inconclusive: {exc}",
                }
            )

        # Check 4: listening ports must be expected operational ports only.
        try:
            checks_performed.append("listening_ports")
            self._check_listening_ports(violations)
        except Exception as exc:  # pragma: no cover - defensive
            violations.append(
                {
                    "check": "listening_ports",
                    "severity": "WARN",
                    "detail": f"check inconclusive: {exc}",
                }
            )

        result = {
            "air_gapped": not any(v.get("severity") in {"ALERT", "CRITICAL"} for v in violations),
            "violations": violations,
            "timestamp": self._ts(),
            "checks_performed": checks_performed,
        }
        self._last_result = result
        return result

    def _check_interfaces(self, violations: List[Dict[str, object]]) -> None:
        interface_names: List[str] = []
        sys_path = "/sys/class/net"
        if os.path.isdir(sys_path):
            interface_names = sorted(os.listdir(sys_path))
        else:
            interface_names = [name for _, name in socket.if_nameindex()]

        for name in interface_names:
            if name in self.allowed_interfaces:
                continue
            # Presence of a non-allowed interface with an assigned IP is treated as violation.
            try:
                infos = socket.getaddrinfo(socket.gethostname(), None)
                has_non_loopback_ip = any(
                    info[4] and info[4][0] not in {"127.0.0.1", "::1"} for info in infos
                )
            except Exception:
                has_non_loopback_ip = False

            if has_non_loopback_ip:
                violations.append(
                    {
                        "check": "network_interfaces",
                        "severity": "ALERT",
                        "interface": name,
                        "detail": f"Unexpected active interface detected: {name}",
                    }
                )

    def _check_dns(self, violations: List[Dict[str, object]]) -> None:
        timeout_prev = socket.getdefaulttimeout()
        socket.setdefaulttimeout(2.0)
        try:
            try:
                socket.getaddrinfo("example.com", 80)
                violations.append(
                    {
                        "check": "dns_resolution",
                        "severity": "CRITICAL",
                        "detail": "DNS resolution succeeded for example.com in air-gapped mode.",
                    }
                )
            except Exception:
                # Expected in an air-gapped setting.
                pass
        finally:
            socket.setdefaulttimeout(timeout_prev)

    def _check_outbound_connectivity(self, violations: List[Dict[str, object]]) -> None:
        conn = None
        try:
            conn = socket.create_connection(("8.8.8.8", 53), timeout=2.0)
            violations.append(
                {
                    "check": "outbound_connectivity",
                    "severity": "CRITICAL",
                    "detail": "Outbound connection to 8.8.8.8:53 succeeded.",
                }
            )
        except Exception:
            # Expected in an air-gapped setting.
            return
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _check_listening_ports(self, violations: List[Dict[str, object]]) -> None:
        allowed_ports = set(self.get_allowed_ports())
        tcp_file = "/proc/net/tcp"
        if not os.path.isfile(tcp_file):
            violations.append(
                {
                    "check": "listening_ports",
                    "severity": "WARN",
                    "detail": "Linux /proc/net/tcp unavailable; check inconclusive.",
                }
            )
            return

        with open(tcp_file, "r", encoding="utf-8") as handle:
            lines = [line.strip() for line in handle.readlines()[1:] if line.strip()]

        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            local_addr = parts[1]
            state_hex = parts[3]
            # 0A is TCP_LISTEN
            if state_hex != "0A":
                continue
            try:
                _, port_hex = local_addr.split(":")
                port = int(port_hex, 16)
            except Exception:
                continue
            if port not in allowed_ports:
                violations.append(
                    {
                        "check": "listening_ports",
                        "severity": "ALERT",
                        "port": port,
                        "detail": f"Unexpected listening TCP port: {port}",
                    }
                )

    def run_continuous(self, callback: Optional[Callable[[Dict[str, object]], None]] = None) -> None:
        """Run verification loop in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()

        def _worker() -> None:
            while not self._stop_event.is_set():
                result = self.verify()
                if callback:
                    try:
                        callback(result)
                    except Exception:
                        # Callback failures must not stop monitoring.
                        pass
                self._stop_event.wait(self.check_interval_seconds)

        self._thread = threading.Thread(target=_worker, daemon=True, name="airgap-verifier")
        self._thread.start()

    def stop_continuous(self) -> None:
        """Stop background verification loop if running."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def get_last_result(self) -> Optional[Dict[str, object]]:
        return self._last_result
