"""Runtime mode and local service control for World Intelligence gateway.

Military/tactical context:
Command systems require deterministic mode control so intelligence feeds can
degrade safely without triggering training or data-sync side effects.
"""

from __future__ import annotations

import subprocess
import threading
import time
import os
import shutil
from typing import Callable
from urllib.parse import urlparse

import requests

from .models import (
    LocalRuntimeHealth,
    ServiceActionResult,
    WorldIntelligenceMode,
)


ServiceRunner = Callable[[str, str], ServiceActionResult]
DEFAULT_LOCAL_RUNTIME_URL = "http://127.0.0.1:8095"
LOCAL_RUNTIME_URL_ENV = "WORLD_INTELLIGENCE_LOCAL_URL"
LOCAL_RUNTIME_FALLBACK_URL_ENV = "WORLD_INTELLIGENCE_LOCAL_RUNTIME_URL"
MODE_ENV = "WORLD_INTELLIGENCE_MODE"


def _configured_local_runtime_url(local_runtime_url: str | None = None) -> str:
    raw_url = (local_runtime_url or "").strip()
    source_name = "local_runtime_url"
    if not raw_url:
        for env_name in (LOCAL_RUNTIME_URL_ENV, LOCAL_RUNTIME_FALLBACK_URL_ENV):
            raw_url = (os.getenv(env_name) or "").strip()
            source_name = env_name
            if raw_url:
                break
    if not raw_url:
        raw_url = DEFAULT_LOCAL_RUNTIME_URL
        source_name = "DEFAULT_LOCAL_RUNTIME_URL"

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{source_name} must be an http(s) URL with a host")
    if parsed.username or parsed.password:
        raise ValueError(f"{source_name} must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{source_name} must not include query strings or fragments")
    return raw_url.rstrip("/")


def _configured_mode(mode: WorldIntelligenceMode | str | None = None) -> WorldIntelligenceMode:
    raw_mode = mode.value if isinstance(mode, WorldIntelligenceMode) else (mode or os.getenv(MODE_ENV, ""))
    normalized_mode = raw_mode.strip().lower().replace("-", "_")
    if not normalized_mode:
        return WorldIntelligenceMode.LOCAL_SELF_HOSTED
    aliases = {
        "local": WorldIntelligenceMode.LOCAL_SELF_HOSTED,
        "local_self_hosted": WorldIntelligenceMode.LOCAL_SELF_HOSTED,
        "external": WorldIntelligenceMode.EXTERNAL_LIVE,
        "external_live": WorldIntelligenceMode.EXTERNAL_LIVE,
        "demo": WorldIntelligenceMode.EXTERNAL_LIVE,
        "demo_external": WorldIntelligenceMode.EXTERNAL_LIVE,
        "external_fallback": WorldIntelligenceMode.EXTERNAL_LIVE_FALLBACK,
        "external_live_fallback": WorldIntelligenceMode.EXTERNAL_LIVE_FALLBACK,
        "training_safe": WorldIntelligenceMode.TRAINING_SAFE,
        "offline_safe": WorldIntelligenceMode.OFFLINE_SAFE,
    }
    try:
        return aliases[normalized_mode]
    except KeyError as exc:
        allowed = ", ".join(sorted(aliases))
        raise ValueError(f"{MODE_ENV} must be one of: {allowed}") from exc


class RuntimeManager:
    """Thread-safe mode manager for local World Intelligence runtime."""

    def __init__(
        self,
        local_runtime_url: str | None = None,
        mode: WorldIntelligenceMode | str | None = None,
        service_name: str = "s3m-world-intelligence",
        request_timeout_seconds: float = 2.5,
        service_timeout_seconds: float = 5.0,
        fallback_enabled: bool = True,
        service_runner: ServiceRunner | None = None,
    ) -> None:
        self.local_runtime_url = _configured_local_runtime_url(local_runtime_url)
        self.service_name = service_name
        self.request_timeout_seconds = request_timeout_seconds
        self.service_timeout_seconds = service_timeout_seconds
        self.fallback_enabled = fallback_enabled
        self._service_runner = service_runner
        self._mode = _configured_mode(mode)
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

    def systemd_control_available(self) -> bool:
        """Report whether this process can attempt host service control."""
        if self._service_runner is not None:
            return True
        return shutil.which("systemctl") is not None

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
                detail="systemctl unavailable in API container",
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
        health_urls = [self.local_runtime_url, f"{self.local_runtime_url}/health"]
        last_error: str | None = None
        last_status_code: int | None = None
        last_endpoint = self.local_runtime_url
        for endpoint in health_urls:
            try:
                response = requests.get(endpoint, timeout=self.request_timeout_seconds)
                last_endpoint = endpoint
                last_status_code = response.status_code
                if response.status_code == 200:
                    return LocalRuntimeHealth(
                        healthy=True,
                        status="healthy",
                        endpoint=endpoint,
                        status_code=response.status_code,
                        detail="local runtime responded",
                    )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
        if last_status_code is not None:
            return LocalRuntimeHealth(
                healthy=False,
                status="unhealthy",
                endpoint=last_endpoint,
                status_code=last_status_code,
                detail=f"local runtime returned HTTP {last_status_code}",
            )
        return LocalRuntimeHealth(
            healthy=False,
            status="down",
            endpoint=last_endpoint,
            detail=last_error or "local runtime unreachable",
        )
