"""Tool registry and guarded tool execution for agent runtime."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

if False:  # pragma: no cover
    from .subagent import PermissionSet


@dataclass(slots=True)
class ToolSpec:
    """Definition for one callable tool in the orchestration runtime."""

    name: str
    handler: Callable[[Dict[str, Any]], Any]
    risk_level: str
    description: str
    parameter_schema: Dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    """Execution result envelope for tool invocations."""

    name: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    risk_level: str = "unknown"


class ToolRegistry:
    """
    Register and execute tools available to orchestrator and subagents.

    Tactical context:
    Tool execution is centrally gated so mission agents cannot bypass safety
    controls when interacting with host systems or mission data stores.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self._register_default_tools()

    def register_tool(
        self,
        name: str,
        handler: Callable[[Dict[str, Any]], Any],
        risk_level: str,
        description: str,
        parameter_schema: Dict[str, Any],
    ) -> None:
        self._tools[name] = ToolSpec(
            name=name,
            handler=handler,
            risk_level=risk_level,
            description=description,
            parameter_schema=parameter_schema,
        )

    def get_tool(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        return self._tools[name]

    def list_tools(self) -> List[str]:
        return sorted(self._tools.keys())

    def execute_tool(self, name: str, parameters: Dict[str, Any], agent_permissions: Any) -> ToolResult:
        spec = self.get_tool(name)
        allowed, reason = self._check_permissions(name=name, parameters=parameters, permissions=agent_permissions)
        if not allowed:
            return ToolResult(
                name=name,
                success=False,
                error=reason,
                risk_level=spec.risk_level,
            )
        try:
            output = spec.handler(parameters)
            return ToolResult(name=name, success=True, output=output, risk_level=spec.risk_level)
        except Exception as exc:  # pragma: no cover - defensive runtime protection
            return ToolResult(
                name=name,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                risk_level=spec.risk_level,
            )

    def _check_permissions(self, name: str, parameters: Dict[str, Any], permissions: Any) -> tuple[bool, str]:
        allowed_tools = set(getattr(permissions, "allowed_tools", []) or [])
        if allowed_tools and "*" not in allowed_tools and name not in allowed_tools:
            return False, f"Tool '{name}' is not allowed by permission set"

        allowed_paths = list(getattr(permissions, "allowed_paths", []) or [])
        if name.startswith("file_") and allowed_paths:
            raw_path = str(parameters.get("path", ""))
            if raw_path:
                resolved = os.path.abspath(raw_path)
                if not any(resolved.startswith(os.path.abspath(root)) for root in allowed_paths):
                    return False, f"Path '{resolved}' is outside allowed paths"

        network_allowlist = set(getattr(permissions, "network_allowlist", []) or [])
        if name in {"api_call", "web_search"} and network_allowlist:
            url = str(parameters.get("url") or parameters.get("endpoint") or "")
            if url:
                host = urlparse(url).netloc
                if host and host not in network_allowlist:
                    return False, f"Host '{host}' is not in network allowlist"

        return True, ""

    def _register_default_tools(self) -> None:
        self.register_tool(
            name="bash_execute",
            handler=self._bash_execute,
            risk_level="high",
            description="Execute a shell command",
            parameter_schema={"command": "str", "timeout_seconds": "int?"},
        )
        self.register_tool(
            name="file_read",
            handler=self._file_read,
            risk_level="low",
            description="Read a UTF-8 text file",
            parameter_schema={"path": "str"},
        )
        self.register_tool(
            name="file_write",
            handler=self._file_write,
            risk_level="medium",
            description="Write UTF-8 text to a file",
            parameter_schema={"path": "str", "content": "str"},
        )
        self.register_tool(
            name="file_delete",
            handler=self._file_delete,
            risk_level="high",
            description="Delete a file from disk",
            parameter_schema={"path": "str"},
        )
        self.register_tool(
            name="python_execute",
            handler=self._python_execute,
            risk_level="high",
            description="Execute Python source in sandboxed scope",
            parameter_schema={"code": "str"},
        )
        self.register_tool(
            name="api_call",
            handler=self._network_blocked,
            risk_level="medium",
            description="HTTP call (disabled in offline runtime)",
            parameter_schema={"url": "str", "method": "str?"},
        )
        self.register_tool(
            name="web_search",
            handler=self._network_blocked,
            risk_level="low",
            description="Web search (disabled in offline runtime)",
            parameter_schema={"query": "str"},
        )
        self.register_tool(
            name="git_operation",
            handler=self._git_operation,
            risk_level="medium-high",
            description="Run guarded git command",
            parameter_schema={"args": "List[str]", "cwd": "str?"},
        )
        self.register_tool(
            name="database_query",
            handler=self._database_query,
            risk_level="medium",
            description="Run read-only database query via adapter",
            parameter_schema={"adapter": "Callable", "query": "str"},
        )
        self.register_tool(
            name="database_mutate",
            handler=self._database_mutate,
            risk_level="high",
            description="Run state-changing database command via adapter",
            parameter_schema={"adapter": "Callable", "statement": "str"},
        )

    @staticmethod
    def _bash_execute(parameters: Dict[str, Any]) -> Dict[str, Any]:
        command = str(parameters.get("command", "")).strip()
        if not command:
            raise ValueError("command is required")
        timeout = int(parameters.get("timeout_seconds", 30))
        completed = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    @staticmethod
    def _file_read(parameters: Dict[str, Any]) -> str:
        path = str(parameters.get("path", "")).strip()
        if not path:
            raise ValueError("path is required")
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    @staticmethod
    def _file_write(parameters: Dict[str, Any]) -> Dict[str, Any]:
        path = str(parameters.get("path", "")).strip()
        if not path:
            raise ValueError("path is required")
        content = str(parameters.get("content", ""))
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return {"bytes_written": len(content.encode("utf-8")), "path": path}

    @staticmethod
    def _file_delete(parameters: Dict[str, Any]) -> Dict[str, Any]:
        path = str(parameters.get("path", "")).strip()
        if not path:
            raise ValueError("path is required")
        if os.path.exists(path):
            os.remove(path)
            return {"deleted": True, "path": path}
        return {"deleted": False, "path": path}

    @staticmethod
    def _python_execute(parameters: Dict[str, Any]) -> Dict[str, Any]:
        code = str(parameters.get("code", "")).strip()
        if not code:
            raise ValueError("code is required")
        local_vars: Dict[str, Any] = {}
        exec(compile(code, "<tool-python-execute>", "exec"), {}, local_vars)  # noqa: S102
        return {"locals": local_vars}

    @staticmethod
    def _network_blocked(_: Dict[str, Any]) -> Dict[str, Any]:
        return {"blocked": True, "reason": "External network calls are disabled in offline deployment"}

    @staticmethod
    def _git_operation(parameters: Dict[str, Any]) -> Dict[str, Any]:
        args = parameters.get("args")
        if not isinstance(args, list) or not args:
            raise ValueError("args must be a non-empty list")
        command = ["git", *[str(item) for item in args]]
        cwd = str(parameters.get("cwd", os.getcwd()))
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=int(parameters.get("timeout_seconds", 30)),
            cwd=cwd,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "command": command,
        }

    @staticmethod
    def _database_query(parameters: Dict[str, Any]) -> Any:
        adapter = parameters.get("adapter")
        query = str(parameters.get("query", "")).strip()
        if not callable(adapter):
            raise ValueError("adapter must be callable")
        if not query:
            raise ValueError("query is required")
        return adapter(query, mutate=False)

    @staticmethod
    def _database_mutate(parameters: Dict[str, Any]) -> Any:
        adapter = parameters.get("adapter")
        statement = str(parameters.get("statement", "")).strip()
        if not callable(adapter):
            raise ValueError("adapter must be callable")
        if not statement:
            raise ValueError("statement is required")
        return adapter(statement, mutate=True)
