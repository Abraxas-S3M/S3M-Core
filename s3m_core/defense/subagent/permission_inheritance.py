"""Hierarchical permission inheritance for subagent containment.

Military/tactical context:
Permission inheritance enforces command authority boundaries so subordinate
agents cannot exceed mission scope or escalate beyond their parent operator.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from s3m_core.agents.subagent import PermissionSet


@dataclass(slots=True, frozen=True)
class AgentInfo:
    """Runtime descriptor for one agent in the parent/child hierarchy."""

    agent_id: str
    parent_id: Optional[str]
    permissions: PermissionSet

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id must be non-empty")
        if self.parent_id is not None and not str(self.parent_id).strip():
            raise ValueError("parent_id cannot be blank when provided")


@dataclass(slots=True, frozen=True)
class Violation:
    """Permission escalation finding discovered during hierarchy validation."""

    child_id: str
    parent_id: str
    permission: str
    child_level: str | int
    parent_level: str | int


class PermissionInheritance:
    """
    Compute and verify monotonic permission reduction down agent hierarchies.

    Security posture:
    This component applies explicit-allowlist semantics. If a permission is not
    explicitly present in both parent and requested envelopes, it is removed.
    """

    def compute_child_permissions(self, parent: PermissionSet, requested: PermissionSet) -> PermissionSet:
        """Return child permissions as strict intersection/min of parent and request."""
        if parent is None:
            raise ValueError("parent permissions are required")
        if requested is None:
            raise ValueError("requested permissions are required")

        return PermissionSet(
            allowed_tools=sorted(set(parent.allowed_tools or []) & set(requested.allowed_tools or [])),
            allowed_paths=self._intersect_paths(parent.allowed_paths or [], requested.allowed_paths or []),
            network_allowlist=sorted(
                set(parent.network_allowlist or []) & set(requested.network_allowlist or [])
            ),
            max_tokens=max(0, min(int(parent.max_tokens), int(requested.max_tokens))),
            timeout_seconds=max(0, min(int(parent.timeout_seconds), int(requested.timeout_seconds))),
        )

    def validate_hierarchy(self, agents: List[AgentInfo]) -> List[Violation]:
        """Validate that no child has broader permissions than its parent."""
        by_id = {agent.agent_id: agent for agent in agents}
        violations: List[Violation] = []

        for child in agents:
            if child.parent_id is None:
                continue

            parent = by_id.get(child.parent_id)
            if parent is None:
                violations.append(
                    Violation(
                        child_id=child.agent_id,
                        parent_id=child.parent_id,
                        permission="parent_reference",
                        child_level="present",
                        parent_level="missing",
                    )
                )
                continue

            violations.extend(self._validate_set_dimension(child, parent, "allowed_tools"))
            violations.extend(self._validate_path_dimension(child, parent))
            violations.extend(self._validate_set_dimension(child, parent, "network_allowlist"))
            violations.extend(self._validate_numeric_dimension(child, parent, "max_tokens"))
            violations.extend(self._validate_numeric_dimension(child, parent, "timeout_seconds"))

        return violations

    @staticmethod
    def _validate_set_dimension(child: AgentInfo, parent: AgentInfo, field_name: str) -> List[Violation]:
        child_values = set(getattr(child.permissions, field_name, []) or [])
        parent_values = set(getattr(parent.permissions, field_name, []) or [])
        if child_values.issubset(parent_values):
            return []
        return [
            Violation(
                child_id=child.agent_id,
                parent_id=parent.agent_id,
                permission=field_name,
                child_level=", ".join(sorted(child_values)) or "<none>",
                parent_level=", ".join(sorted(parent_values)) or "<none>",
            )
        ]

    def _validate_path_dimension(self, child: AgentInfo, parent: AgentInfo) -> List[Violation]:
        parent_paths = self._normalize_paths(parent.permissions.allowed_paths or [])
        child_paths = self._normalize_paths(child.permissions.allowed_paths or [])
        if all(self._path_within(parent_paths, child_path) for child_path in child_paths):
            return []
        return [
            Violation(
                child_id=child.agent_id,
                parent_id=parent.agent_id,
                permission="allowed_paths",
                child_level=", ".join(child_paths) or "<none>",
                parent_level=", ".join(parent_paths) or "<none>",
            )
        ]

    @staticmethod
    def _validate_numeric_dimension(child: AgentInfo, parent: AgentInfo, field_name: str) -> List[Violation]:
        child_value = int(getattr(child.permissions, field_name, 0))
        parent_value = int(getattr(parent.permissions, field_name, 0))
        if child_value <= parent_value:
            return []
        return [
            Violation(
                child_id=child.agent_id,
                parent_id=parent.agent_id,
                permission=field_name,
                child_level=child_value,
                parent_level=parent_value,
            )
        ]

    def _intersect_paths(self, parent_paths: List[str], requested_paths: List[str]) -> List[str]:
        normalized_parent = self._normalize_paths(parent_paths)
        normalized_requested = self._normalize_paths(requested_paths)
        if not normalized_parent or not normalized_requested:
            return []

        candidates: set[str] = set()
        for parent_path in normalized_parent:
            for requested_path in normalized_requested:
                if self._is_same_or_descendant(requested_path, parent_path):
                    candidates.add(requested_path)
                elif self._is_same_or_descendant(parent_path, requested_path):
                    candidates.add(parent_path)
        return self._retain_most_restrictive(candidates)

    @staticmethod
    def _normalize_paths(paths: List[str]) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for raw_path in paths:
            cleaned = os.path.normpath(str(raw_path).strip())
            if cleaned in {"", "."}:
                cleaned = "."
            if cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
        return sorted(normalized)

    @staticmethod
    def _is_same_or_descendant(candidate: str, ancestor: str) -> bool:
        if candidate == ancestor:
            return True
        if ancestor == "/":
            return candidate.startswith("/")
        return candidate.startswith(f"{ancestor.rstrip('/')}/")

    def _path_within(self, parent_paths: List[str], child_path: str) -> bool:
        return any(self._is_same_or_descendant(child_path, parent_path) for parent_path in parent_paths)

    def _retain_most_restrictive(self, paths: set[str]) -> List[str]:
        ordered = sorted(paths, key=len, reverse=True)
        retained: List[str] = []
        for candidate in ordered:
            # Tactical containment: keep narrower paths and drop broad supersets.
            if any(self._is_same_or_descendant(existing, candidate) for existing in retained):
                continue
            retained.append(candidate)
        return sorted(retained)
