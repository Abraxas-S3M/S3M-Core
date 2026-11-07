"""Startup egress assertion for the synthetic cyber range.

Military/tactical context: range runs emulate field SOCs that must never leak
mission data or pull untrusted content during rehearsals.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Sequence

# Documentation / TEST-NET style probe — connection success means egress is open.
_DEFAULT_PROBE_HOST = "203.0.113.53"
_DEFAULT_PROBE_PORT = 443
_PROBE_TIMEOUT_S = 2.0


@dataclass(frozen=True, slots=True)
class EgressProbeResult:
    """Outcome of an outbound connectivity probe."""

    host: str
    port: int
    connected: bool
    detail: str


def probe_external_egress(
    host: str = _DEFAULT_PROBE_HOST,
    port: int = _DEFAULT_PROBE_PORT,
    timeout: float = _PROBE_TIMEOUT_S,
) -> EgressProbeResult:
    """Attempt a TCP connection to an external address (must fail in range)."""
    if not str(host).strip():
        raise ValueError("host must be non-empty")
    if not 1 <= int(port) <= 65535:
        raise ValueError("port must be between 1 and 65535")
    conn = None
    try:
        conn = socket.create_connection((host, port), timeout=timeout)
        return EgressProbeResult(
            host=host,
            port=port,
            connected=True,
            detail="Outbound TCP connection succeeded; range egress is not blocked.",
        )
    except OSError as exc:
        return EgressProbeResult(
            host=host,
            port=port,
            connected=False,
            detail=f"Connection blocked or unreachable as expected: {exc}",
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def assert_range_egress_blocked(
    probe_hosts: Sequence[tuple[str, int]] | None = None,
    timeout: float = _PROBE_TIMEOUT_S,
) -> None:
    """Fail fast when any probe host accepts a TCP connection."""
    probes = probe_hosts or [(_DEFAULT_PROBE_HOST, _DEFAULT_PROBE_PORT), ("8.8.8.8", 53)]
    successes = []
    for host, port in probes:
        result = probe_external_egress(host=host, port=port, timeout=timeout)
        if result.connected:
            successes.append(f"{host}:{port}")
    if successes:
        joined = ", ".join(successes)
        raise RuntimeError(
            "Range egress guard failed: outbound connectivity succeeded to "
            f"{joined}. Block internet egress before running the cyber range."
        )
