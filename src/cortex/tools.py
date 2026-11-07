"""Forbidden MCP tool classes for Cortex (no arbitrary execution paths)."""

from __future__ import annotations

from typing import Dict

_FORBIDDEN_TOOL_NAMES = frozenset(
    {
        "run_arbitrary_code",
        "execute_shell",
        "bulk_delete",
        "export_credentials",
        "delete_audit_trail",
        "external_port_scan",
        "edit_opa_policy",
        "self_edit_policy",
    }
)


def forbidden_tool_reason(tool_name: str) -> str | None:
    """Return a denial reason when tool_name is disallowed."""
    normalized = str(tool_name or "").strip().lower()
    if normalized in _FORBIDDEN_TOOL_NAMES:
        return f"tool '{normalized}' is forbidden for Cortex agents"
    if normalized.startswith("shell_") or normalized.endswith("_shell"):
        return "shell execution tools are forbidden for Cortex agents"
    return None


def assert_tool_permitted(tool_name: str) -> None:
    """Raise ValueError when a tool must not be registered for Cortex."""
    reason = forbidden_tool_reason(tool_name)
    if reason:
        raise ValueError(reason)
