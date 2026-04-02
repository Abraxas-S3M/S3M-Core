"""Sandbox controller for containerized edge runtime isolation."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from src.edge_compute.models import SandboxState


class SandboxController:
    """Manage isolated sandbox records for tactical training/inference."""

    def __init__(self, runtime: str = "docker", base_image: str = "s3m-sandbox:latest") -> None:
        self.runtime = runtime
        self.base_image = base_image
        self._sandboxes: Dict[str, SandboxState] = {}
        self._runtime_available = False

    def deploy(
        self,
        cpu_cores: int = 2,
        memory_mb: int = 2048,
        gpu_passthrough: bool = False,
        network_isolation: bool = True,
        env_vars: Dict[str, str] | None = None,
        params: Dict[str, Any] | None = None,
    ) -> SandboxState:
        merged_params = dict(params or {})
        if isinstance(env_vars, dict):
            merged_params.setdefault("env", {})
            for key, value in env_vars.items():
                merged_params["env"][str(key)] = str(value)
        sandbox_id = f"sb-{uuid.uuid4().hex[:12]}"
        state = SandboxState(
            sandbox_id=sandbox_id,
            running=True,
            cpu_cores=max(1, int(cpu_cores)),
            memory_mb=max(256, int(memory_mb)),
            gpu_passthrough=bool(gpu_passthrough),
            network_isolation=bool(network_isolation),
            parameters=merged_params,
        )
        self._sandboxes[sandbox_id] = state
        return state

    def update_params(self, sandbox_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None:
            raise ValueError("sandbox not found")
        for key, value in (updates or {}).items():
            sandbox.parameters[str(key)] = value
        return dict(sandbox.parameters)

    def get_params(self, sandbox_id: str) -> Dict[str, Any]:
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None:
            raise ValueError("sandbox not found")
        return dict(sandbox.parameters)

    def stop(self, sandbox_id: str) -> bool:
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None or not sandbox.running:
            return False
        sandbox.running = False
        return True

    def stop_all(self) -> None:
        for state in self._sandboxes.values():
            state.running = False

    def get_logs(self, sandbox_id: str, tail: int = 100) -> List[str]:
        if sandbox_id not in self._sandboxes:
            raise ValueError("sandbox not found")
        n = max(1, min(int(tail), 5000))
        return [f"[sandbox:{sandbox_id}] tactical log line {idx+1}" for idx in range(min(n, 20))]

    def list_sandboxes(self) -> List[SandboxState]:
        return list(self._sandboxes.values())

    def health_check(self) -> Dict[str, object]:
        running = sum(1 for s in self._sandboxes.values() if s.running)
        return {
            "status": "operational",
            "runtime": self.runtime,
            "runtime_available": self._runtime_available,
            "total_sandboxes": len(self._sandboxes),
            "running_sandboxes": running,
        }
