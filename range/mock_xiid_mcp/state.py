"""Shared runtime state for the mock XiiD MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Optional

from range.mock_xiid_mcp.network_model import NetworkModel
from range.mock_xiid_mcp.signing import RecordSigner


@dataclass
class IdempotencyStore:
    """Caches write results keyed by idempotency_key for exactly-once semantics."""

    _entries: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            value = self._entries.get(key)
            return None if value is None else dict(value)

    def put(self, key: str, value: Dict[str, Any]) -> None:
        with self._lock:
            self._entries[key] = dict(value)


@dataclass
class InvocationMetrics:
    """Test hooks: count tool executions and auth failures."""

    tool_calls: Dict[str, int] = field(default_factory=dict)
    write_calls: int = 0
    auth_failures: int = 0
    _lock: RLock = field(default_factory=RLock)

    def record_call(self, tool_name: str, *, is_write: bool, applied: bool = True) -> None:
        with self._lock:
            self.tool_calls[tool_name] = self.tool_calls.get(tool_name, 0) + 1
            if is_write and applied:
                self.write_calls += 1


@dataclass
class MockServerState:
    """Lifespan payload held by the MCP server."""

    model: NetworkModel
    signer: RecordSigner
    idempotency: IdempotencyStore
    metrics: InvocationMetrics
    expected_bearer: str
    rug_pulled_tool: Optional[str] = None
    tool_descriptions: Dict[str, str] = field(default_factory=dict)
    fail_next_write: bool = False
