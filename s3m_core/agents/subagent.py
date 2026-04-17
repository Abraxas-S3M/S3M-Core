"""Scoped subagent worker used by the top-level orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .task_decomposer import SubTask

if TYPE_CHECKING:  # pragma: no cover
    from .orchestrator import AgenticOrchestrator


@dataclass(slots=True)
class PermissionSet:
    """Runtime permission envelope assigned to each subagent."""

    allowed_tools: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    network_allowlist: List[str] = field(default_factory=list)
    max_tokens: int = 2048
    timeout_seconds: int = 120

    def is_equal_or_more_restrictive_than(self, parent: "PermissionSet") -> bool:
        parent_tools = set(parent.allowed_tools or [])
        child_tools = set(self.allowed_tools or [])
        if parent_tools and not child_tools.issubset(parent_tools):
            return False

        parent_paths = [path.rstrip("/") for path in parent.allowed_paths or []]
        child_paths = [path.rstrip("/") for path in self.allowed_paths or []]
        if parent_paths:
            for child_path in child_paths:
                if not any(
                    child_path == parent_path or child_path.startswith(f"{parent_path}/")
                    for parent_path in parent_paths
                ):
                    return False

        parent_hosts = set(parent.network_allowlist or [])
        child_hosts = set(self.network_allowlist or [])
        if parent_hosts and not child_hosts.issubset(parent_hosts):
            return False

        return self.max_tokens <= parent.max_tokens and self.timeout_seconds <= parent.timeout_seconds


@dataclass(slots=True)
class SubAgentResult:
    """Result payload returned by a subagent after subtask execution."""

    agent_id: str
    task_id: str
    success: bool
    output: Dict[str, Any]
    tools_used: List[str] = field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None


class SubAgent:
    """
    Scoped worker that executes one subtask in isolation.

    Tactical context:
    Subagents are constrained execution cells used to parallelize mission work
    without granting broader authority than the parent orchestrator.
    """

    def __init__(
        self,
        agent_id: str,
        model: Any,
        tokenizer: Any,
        parent_orchestrator: "AgenticOrchestrator",
        task: SubTask,
        tools: List[str],
        permissions: PermissionSet,
    ) -> None:
        self.agent_id = agent_id
        self.model = model
        self.tokenizer = tokenizer
        self.parent_orchestrator = parent_orchestrator
        self.task = task
        self.tools = list(tools)
        self.permissions = permissions
        parent_permissions = getattr(parent_orchestrator, "permission_set", permissions)
        if not self.permissions.is_equal_or_more_restrictive_than(parent_permissions):
            raise ValueError("Subagent permissions must be equal to or more restrictive than the parent")

    def execute(self) -> SubAgentResult:
        audit: List[Dict[str, Any]] = [self._event("subagent_started", {"task_id": self.task.task_id})]
        outputs: Dict[str, Any] = {}
        tools_used: List[str] = []
        for tool_name in self.task.required_tools:
            if self.tools and tool_name not in self.tools:
                return SubAgentResult(
                    agent_id=self.agent_id,
                    task_id=self.task.task_id,
                    success=False,
                    output=outputs,
                    tools_used=tools_used,
                    audit_trail=audit + [self._event("tool_blocked", {"tool": tool_name})],
                    error=f"Tool '{tool_name}' not assigned to subagent",
                )
            tool_result = self.parent_orchestrator.invoke_tool(
                name=tool_name,
                parameters={"task_description": self.task.description},
                permissions=self.permissions,
                subagent_id=self.agent_id,
                task_id=self.task.task_id,
            )
            tools_used.append(tool_name)
            outputs[tool_name] = tool_result.output if tool_result.success else tool_result.error
            audit.append(self._event("tool_executed", {"tool": tool_name, "success": tool_result.success}))
            if not tool_result.success:
                return SubAgentResult(
                    agent_id=self.agent_id,
                    task_id=self.task.task_id,
                    success=False,
                    output=outputs,
                    tools_used=tools_used,
                    audit_trail=audit,
                    error=tool_result.error or f"Tool '{tool_name}' failed",
                )

        if not self.task.required_tools:
            outputs["analysis"] = self._generate_reasoned_output()
            audit.append(self._event("reasoning_complete", {"mode": "model_or_fallback"}))

        result = SubAgentResult(
            agent_id=self.agent_id,
            task_id=self.task.task_id,
            success=True,
            output={
                "task_description": self.task.description,
                "details": outputs,
            },
            tools_used=tools_used,
            audit_trail=audit + [self._event("subagent_completed", {"success": True})],
        )
        return result

    def report_to_parent(self, result: SubAgentResult) -> None:
        self.parent_orchestrator.receive_subagent_report(self.agent_id, result)

    def _generate_reasoned_output(self) -> str:
        generator = getattr(self.model, "generate", None)
        if callable(generator):
            try:
                return str(generator(self.task.description))
            except Exception:
                pass
        return f"Subtask '{self.task.description}' completed using fallback reasoning."

    @staticmethod
    def _event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": event_type,
            "payload": dict(payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
