"""Runtime mode and local service control for World Intelligence gateway.

Military/tactical context:
Command systems require deterministic mode control so intelligence feeds can
degrade safely without triggering training or data-sync side effects.
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Callable

import requests

from .models import (
    LocalRuntimeHealth,
    ServiceActionResult,
    WorldIntelligenceMode,
)


ServiceRunner = Callable[[str, str], ServiceActionResult]


class RuntimeManager:
    """Thread-safe mode manager for local World Intelligence runtime."""

    def __init__(
        self,
        local_runtime_url: str = "http://127.0.0.1:8095",
        service_name: str = "s3m-world-intelligence",
        request_timeout_seconds: float = 2.5,
        service_timeout_seconds: float = 5.0,
        fallback_enabled: bool = True,
        service_runner: ServiceRunner | None = None,
    ) -> None:
        self.local_runtime_url = local_runtime_url.rstrip("/")
        self.service_name = service_name
        self.request_timeout_seconds = request_timeout_seconds
        self.service_timeout_seconds = service_timeout_seconds
        self.fallback_enabled = fallback_enabled
        self._service_runner = service_runner
        self._mode = WorldIntelligenceMode.LOCAL_SELF_HOSTED
        self._lock = threading.Lock()

    def get_mode(self) -> WorldIntelligenceMode:
        with self._lock:
            return self._mode

    def set_mode(self, mode: WorldIntelligenceMode) -> ServiceActionResult | None:
        """Set operating mode and enforce training-safe local stop."""
        with self._lock:
            self._mode = mode
        if mode == WorldIntelligenceMode.TRAINING_SAFE:
            # Tactical training-safe posture forces local runtime halt.
            return self.stop_local_runtime()
        return None

    def restart_local_runtime(self) -> ServiceActionResult:
        """Manual restart; blocked while explicitly in training-safe mode."""
        if self.get_mode() == WorldIntelligenceMode.TRAINING_SAFE:
            return ServiceActionResult(
                ok=False,
                action="restart",
                service=self.service_name,
                detail="restart blocked while mode is training_safe",
            )
        return self._run_service_action("restart")

    def stop_local_runtime(self) -> ServiceActionResult:
        return self._run_service_action("stop")

    def start_local_runtime(
        self,
        startup_wait_seconds: float = 1.0,
    ) -> tuple[ServiceActionResult, LocalRuntimeHealth]:
        """Start local runtime and perform a single bounded health check."""
        start_result = self._run_service_action("start")
        if start_result.ok and startup_wait_seconds > 0:
            time.sleep(min(startup_wait_seconds, self.service_timeout_seconds))
        return start_result, self.local_runtime_health()

    def local_service_state(self) -> ServiceActionResult:
        return self._run_service_action("is-active")

    def _run_service_action(self, action: str) -> ServiceActionResult:
        if self._service_runner is not None:
            return self._service_runner(action, self.service_name)
        try:
            proc = subprocess.run(
                ["systemctl", action, self.service_name],
                capture_output=True,
                text=True,
                timeout=self.service_timeout_seconds,
                check=False,
            )
            detail = (proc.stdout or proc.stderr or "").strip()
            ok = proc.returncode == 0
            return ServiceActionResult(
                ok=ok,
                action=action,
                service=self.service_name,
                detail=detail if detail else ("ok" if ok else "failed"),
            )
        except FileNotFoundError:
            return ServiceActionResult(
                ok=False,
                action=action,
                service=self.service_name,
                detail="systemctl unavailable on host",
            )
        except subprocess.TimeoutExpired:
            return ServiceActionResult(
                ok=False,
                action=action,
                service=self.service_name,
                detail="service action timed out",
            )

    def local_runtime_health(self) -> LocalRuntimeHealth:
        """Probe local runtime endpoint with bounded timeout."""
        health_urls = [f"{self.local_runtime_url}/health", self.local_runtime_url]
        for endpoint in health_urls:
            try:
                response = requests.get(endpoint, timeout=self.request_timeout_seconds)
                if response.status_code < 500:
                    return LocalRuntimeHealth(
                        healthy=True,
                        status="healthy",
                        endpoint=endpoint,
                        status_code=response.status_code,
                        detail="local runtime responded",
                    )
                return LocalRuntimeHealth(
                    healthy=False,
                    status="unhealthy",
                    endpoint=endpoint,
                    status_code=response.status_code,
                    detail="local runtime server error",
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
        return LocalRuntimeHealth(
            healthy=False,
            status="down",
            endpoint=self.local_runtime_url,
            detail=last_error if "last_error" in locals() else "local runtime unreachable",
        )
