"""Low-level change applicators reachable only through CortexBroker."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Dict


_BROKER_AUTH: ContextVar[bool] = ContextVar("cortex_broker_authorized", default=False)


class BrokerBypassError(RuntimeError):
    """Raised when a network/system change bypasses policy_gate and broker."""


@dataclass(frozen=True, slots=True)
class NetworkChange:
    """Describes an outbound or lateral network mutation."""

    destination: str
    operation: str
    metadata: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class SystemChange:
    """Describes a host or mission-system state mutation."""

    target: str
    operation: str
    metadata: Dict[str, Any]


def broker_authorize() -> Token:
    """Mark the current context as broker-authorized (internal use)."""
    return _BROKER_AUTH.set(True)


def broker_reset(token: Token) -> None:
    _BROKER_AUTH.reset(token)


def _require_broker() -> None:
    if not _BROKER_AUTH.get():
        raise BrokerBypassError(
            "network and system changes must flow through src.cortex.broker.CortexBroker"
        )


def apply_network_change(change: NetworkChange) -> Dict[str, Any]:
    """Apply a network change after broker authorization."""
    _require_broker()
    return {
        "applied": True,
        "kind": "network",
        "destination": change.destination,
        "operation": change.operation,
    }


def apply_system_change(change: SystemChange) -> Dict[str, Any]:
    """Apply a system change after broker authorization."""
    _require_broker()
    return {
        "applied": True,
        "kind": "system",
        "target": change.target,
        "operation": change.operation,
    }
