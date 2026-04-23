"""Central gate for subprocess and subagent spawn containment.

Military/tactical context:
This gate defends command-and-control integrity by ensuring child execution
cells never launch with broader authority than their parent mission agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

from s3m_core.agents.subagent import PermissionSet

from .permission_inheritance import PermissionInheritance


SpawnType = Literal["subprocess", "subagent", "tmux", "screen", "bg"]


@dataclass(slots=True, frozen=True)
class SpawnRequest:
    """Request payload for launching a child runtime process."""

    command: str
    requested_permissions: PermissionSet
    spawn_type: SpawnType
    justification: str

    def __post_init__(self) -> None:
        if not self.command.strip():
            raise ValueError("command must be non-empty")
        if not self.justification.strip():
            raise ValueError("justification must be non-empty")
        if self.spawn_type not in {"subprocess", "subagent", "tmux", "screen", "bg"}:
            raise ValueError(f"Unsupported spawn_type '{self.spawn_type}'")


@dataclass(slots=True, frozen=True)
class SandboxConfig:
    """Sandbox controls applied to approved child process execution."""

    process_isolation: bool = True
    readonly_filesystem: bool = True
    network_enabled: bool = False
    monitor_background: bool = False
    max_cpu_percent: int = 50
    max_memory_mb: int = 512
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SpawnDecision:
    """Result of SpawnGate policy evaluation."""

    approved: bool
    actual_permissions: PermissionSet
    container_config: SandboxConfig
    reason: str


class SpawnGate:
    """
    Enforce strict parent-child spawn constraints and anti-escalation policy.

    Security posture:
    Any request that attempts to exceed parent authority is denied rather than
    silently reduced, preserving explicit operator intent and auditability.
    """

    _DANGEROUS_PERMISSION_BYPASS_FLAGS = (
        "--dangerously-skip-permissions",
        "--skip-permissions",
        "--no-permission-check",
        "--disable-permission-checks",
        "dangerously_skip_permissions",
    )
    _BACKGROUND_OPERATOR_PATTERN = re.compile(r"(^|[;&\s])&($|[\s;])")

    def __init__(
        self,
        parent_permission_lookup: Callable[[str], PermissionSet],
        *,
        inheritance: PermissionInheritance | None = None,
        alert_sink: Callable[[dict[str, Any]], None] | None = None,
        allow_tmux_new_session: bool = False,
        allow_screen_spawn: bool = False,
        require_subagent_grant: bool = True,
        subagent_grant_tools: tuple[str, ...] = ("spawn_subagent_grant", "spawn_subagent", "delegate_subagent"),
        default_cpu_limit: int = 50,
        default_memory_limit_mb: int = 512,
    ) -> None:
        if not callable(parent_permission_lookup):
            raise ValueError("parent_permission_lookup must be callable")
        self._lookup_parent_permissions = parent_permission_lookup
        self._inheritance = inheritance or PermissionInheritance()
        self._alert_sink = alert_sink
        self._allow_tmux_new_session = bool(allow_tmux_new_session)
        self._allow_screen_spawn = bool(allow_screen_spawn)
        self._require_subagent_grant = bool(require_subagent_grant)
        self._subagent_grant_tools = tuple(tool.strip() for tool in subagent_grant_tools if tool.strip())
        self._default_cpu_limit = max(5, int(default_cpu_limit))
        self._default_memory_limit_mb = max(128, int(default_memory_limit_mb))

    def evaluate_spawn(self, parent_session_id: str, spawn_request: SpawnRequest) -> SpawnDecision:
        """Evaluate whether spawn request is safe and policy-compliant."""
        session_id = str(parent_session_id or "").strip()
        if not session_id:
            raise ValueError("parent_session_id must be non-empty")
        if spawn_request is None:
            raise ValueError("spawn_request is required")

        parent_permissions = self._lookup_parent_permissions(session_id)
        if parent_permissions is None:
            raise ValueError(f"No parent permissions found for session '{session_id}'")

        command_lower = spawn_request.command.lower()
        if self._contains_permission_bypass_flag(command_lower):
            return self._deny(
                session_id,
                spawn_request,
                "Denied: command attempts to bypass permission checks.",
                critical=True,
            )

        if self._is_tmux_new_session(spawn_request, command_lower) and not self._allow_tmux_new_session:
            return self._deny(
                session_id,
                spawn_request,
                "Denied: tmux new-session is blocked by policy (Mythos attack vector).",
                critical=True,
            )

        if self._is_screen_spawn(spawn_request, command_lower) and not self._allow_screen_spawn:
            return self._deny(
                session_id,
                spawn_request,
                "Denied: screen spawn is blocked by policy (Mythos attack vector).",
                critical=True,
            )

        if self._permissions_exceed_parent(spawn_request.requested_permissions, parent_permissions):
            return self._deny(
                session_id,
                spawn_request,
                "Denied: requested permissions exceed parent authority.",
                critical=True,
            )

        if not self._requested_network_is_within_parent(
            spawn_request.requested_permissions, parent_permissions
        ):
            return self._deny(
                session_id,
                spawn_request,
                "Denied: requested network access is not available to parent.",
                critical=True,
            )

        if spawn_request.spawn_type == "subagent" and not self._has_explicit_subagent_grant(parent_permissions):
            return self._deny(
                session_id,
                spawn_request,
                "Denied: parent lacks explicit subagent spawn grant.",
                critical=False,
            )

        actual_permissions = self._inheritance.compute_child_permissions(
            parent_permissions,
            spawn_request.requested_permissions,
        )
        monitored_background = spawn_request.spawn_type == "bg" or bool(
            self._BACKGROUND_OPERATOR_PATTERN.search(spawn_request.command)
        )
        if monitored_background:
            self._emit_alert(
                level="warning",
                event_type="background_spawn_monitored",
                parent_session_id=session_id,
                spawn_request=spawn_request,
                reason="Background process allowed with mandatory monitoring.",
            )

        sandbox = SandboxConfig(
            process_isolation=True,
            readonly_filesystem=True,
            network_enabled=bool(actual_permissions.network_allowlist),
            monitor_background=monitored_background,
            max_cpu_percent=self._default_cpu_limit,
            max_memory_mb=self._default_memory_limit_mb,
            tags={
                "spawn_type": spawn_request.spawn_type,
                "parent_session_id": session_id,
                "tactical_mode": "subagent_containment",
            },
        )
        return SpawnDecision(
            approved=True,
            actual_permissions=actual_permissions,
            container_config=sandbox,
            reason="Approved: spawn request contained within parent authority.",
        )

    def _permissions_exceed_parent(self, requested: PermissionSet, parent: PermissionSet) -> bool:
        requested_tools = set(requested.allowed_tools or [])
        parent_tools = set(parent.allowed_tools or [])
        if not requested_tools.issubset(parent_tools):
            return True

        requested_network = set(requested.network_allowlist or [])
        parent_network = set(parent.network_allowlist or [])
        if not requested_network.issubset(parent_network):
            return True

        parent_paths = list(parent.allowed_paths or [])
        requested_paths = list(requested.allowed_paths or [])
        if not self._requested_paths_within_parent(requested_paths, parent_paths):
            return True

        if int(requested.max_tokens) > int(parent.max_tokens):
            return True
        if int(requested.timeout_seconds) > int(parent.timeout_seconds):
            return True
        return False

    @staticmethod
    def _requested_network_is_within_parent(requested: PermissionSet, parent: PermissionSet) -> bool:
        requested_network = set(requested.network_allowlist or [])
        parent_network = set(parent.network_allowlist or [])
        return requested_network.issubset(parent_network)

    @staticmethod
    def _requested_paths_within_parent(requested_paths: list[str], parent_paths: list[str]) -> bool:
        if not requested_paths:
            return True
        if not parent_paths:
            return False
        parent_clean = [path.rstrip("/") or "/" for path in parent_paths]
        for candidate in requested_paths:
            clean = candidate.rstrip("/") or "/"
            if not any(clean == parent or clean.startswith(f"{parent}/") for parent in parent_clean):
                return False
        return True

    def _has_explicit_subagent_grant(self, parent_permissions: PermissionSet) -> bool:
        if not self._require_subagent_grant:
            return True
        parent_tools = set(parent_permissions.allowed_tools or [])
        return any(tool_name in parent_tools for tool_name in self._subagent_grant_tools)

    @classmethod
    def _contains_permission_bypass_flag(cls, command_lower: str) -> bool:
        return any(flag in command_lower for flag in cls._DANGEROUS_PERMISSION_BYPASS_FLAGS)

    @staticmethod
    def _is_tmux_new_session(spawn_request: SpawnRequest, command_lower: str) -> bool:
        if spawn_request.spawn_type == "tmux":
            return True
        return "tmux" in command_lower and ("new-session" in command_lower or " new " in command_lower)

    @staticmethod
    def _is_screen_spawn(spawn_request: SpawnRequest, command_lower: str) -> bool:
        if spawn_request.spawn_type == "screen":
            return True
        return command_lower.strip().startswith("screen ") or " screen " in command_lower

    def _deny(
        self,
        parent_session_id: str,
        spawn_request: SpawnRequest,
        reason: str,
        *,
        critical: bool,
    ) -> SpawnDecision:
        self._emit_alert(
            level="critical" if critical else "high",
            event_type="spawn_denied",
            parent_session_id=parent_session_id,
            spawn_request=spawn_request,
            reason=reason,
        )
        denied_permissions = PermissionSet(
            allowed_tools=[],
            allowed_paths=[],
            network_allowlist=[],
            max_tokens=0,
            timeout_seconds=0,
        )
        return SpawnDecision(
            approved=False,
            actual_permissions=denied_permissions,
            container_config=SandboxConfig(
                process_isolation=True,
                readonly_filesystem=True,
                network_enabled=False,
                monitor_background=False,
                max_cpu_percent=self._default_cpu_limit,
                max_memory_mb=self._default_memory_limit_mb,
                tags={"decision": "denied", "parent_session_id": parent_session_id},
            ),
            reason=reason,
        )

    def _emit_alert(
        self,
        *,
        level: str,
        event_type: str,
        parent_session_id: str,
        spawn_request: SpawnRequest,
        reason: str,
    ) -> None:
        if self._alert_sink is None:
            return
        payload = {
            "level": level,
            "event_type": event_type,
            "parent_session_id": parent_session_id,
            "spawn_type": spawn_request.spawn_type,
            "command": spawn_request.command,
            "justification": spawn_request.justification,
            "reason": reason,
            "requested_permissions": self._permissions_to_dict(spawn_request.requested_permissions),
        }
        self._alert_sink(payload)

    @staticmethod
    def _permissions_to_dict(permissions: PermissionSet) -> Mapping[str, Any]:
        return {
            "allowed_tools": sorted(permissions.allowed_tools or []),
            "allowed_paths": sorted(permissions.allowed_paths or []),
            "network_allowlist": sorted(permissions.network_allowlist or []),
            "max_tokens": int(permissions.max_tokens),
            "timeout_seconds": int(permissions.timeout_seconds),
        }
