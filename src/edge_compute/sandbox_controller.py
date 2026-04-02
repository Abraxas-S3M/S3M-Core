"""
S3M Sandbox Controller
UNCLASSIFIED - FOUO

Manages virtualized, isolated deployments of S3M engine instances with
runtime-togglable parameters.

Military/tactical context:
Sandboxed containers let operators test mission behavior changes without
risking the primary battle-network node. Runtime parameter toggling enables
rapid adaptation to contested conditions while preserving service continuity.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from src.edge_compute.models import SandboxState

logger = logging.getLogger("s3m.edge.sandbox")

# Default toggleable parameters.
DEFAULT_PARAMS: Dict[str, Any] = {
    "training_enabled": True,
    "inference_enabled": True,
    "data_generation_enabled": True,
    "replication_enabled": False,
    "max_inference_batch": 32,
    "temperature": 0.7,
    "max_tokens": 512,
    "learning_rate": 0.001,
    "federated_enabled": True,
    "self_training_enabled": True,
    "log_level": "INFO",
}

_ALLOWED_RUNTIMES = {"docker", "podman"}
_MUTABLE_PARAM_TYPES: Dict[str, tuple[type, ...]] = {
    "training_enabled": (bool,),
    "inference_enabled": (bool,),
    "data_generation_enabled": (bool,),
    "replication_enabled": (bool,),
    "max_inference_batch": (int,),
    "temperature": (float, int),
    "max_tokens": (int,),
    "learning_rate": (float, int),
    "federated_enabled": (bool,),
    "self_training_enabled": (bool,),
    "log_level": (str,),
}


class SandboxController:
    """
    Deploys and manages sandboxed S3M engine instances.

    Supports:
      - Docker / Podman container isolation
      - CPU-only and GPU-passthrough modes
      - Runtime parameter toggling via shared JSON config volume
      - Resource limit enforcement (CPU, memory, disk)
      - Log retrieval from running containers
      - Inotify-backed hot-reconfiguration callback (or polling fallback)
    """

    def __init__(
        self,
        runtime: str = "docker",
        base_image: str = "s3m-sandbox:latest",
        work_dir: str = "data/edge/sandboxes/",
        default_params: Optional[Dict[str, Any]] = None,
    ):
        runtime = runtime.strip().lower()
        if runtime not in _ALLOWED_RUNTIMES:
            raise ValueError(f"Unsupported runtime '{runtime}'. Use docker or podman.")
        self.runtime = runtime
        self.base_image = base_image
        self.work_dir = work_dir
        self.default_params = default_params or DEFAULT_PARAMS.copy()
        self._validate_params(self.default_params)

        os.makedirs(work_dir, exist_ok=True)
        self._sandboxes: Dict[str, SandboxState] = {}
        self._runtime_available = shutil.which(runtime) is not None
        self._watchers: Dict[str, threading.Thread] = {}
        self._watcher_stops: Dict[str, threading.Event] = {}

        logger.info(
            "SandboxController: runtime=%s, available=%s",
            runtime,
            self._runtime_available,
        )

    # ── Parameter Management ─────────────────────────────

    def _param_file(self, sandbox_id: str) -> str:
        return os.path.join(self.work_dir, sandbox_id, "params.json")

    def _validate_params(self, params: Dict[str, Any]) -> None:
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        for key, value in params.items():
            if key not in _MUTABLE_PARAM_TYPES:
                raise ValueError(f"Unknown runtime parameter '{key}'")
            expected_types = _MUTABLE_PARAM_TYPES[key]
            if not isinstance(value, expected_types):
                expected = ", ".join(t.__name__ for t in expected_types)
                raise ValueError(
                    f"Parameter '{key}' must be of type {expected}, "
                    f"got {type(value).__name__}"
                )
            # Additional hardening for tactical runtime controls.
            if key in {"max_inference_batch", "max_tokens"} and int(value) <= 0:
                raise ValueError(f"Parameter '{key}' must be > 0")
            if key == "temperature" and not (0.0 <= float(value) <= 2.0):
                raise ValueError("Parameter 'temperature' must be in [0.0, 2.0]")
            if key == "learning_rate" and float(value) <= 0.0:
                raise ValueError("Parameter 'learning_rate' must be > 0")

    def _write_params(self, sandbox_id: str, params: Dict[str, Any]) -> None:
        """Write parameters to the shared volume for the container to pick up."""
        self._validate_params(params)
        param_dir = os.path.join(self.work_dir, sandbox_id)
        os.makedirs(param_dir, exist_ok=True)
        path = self._param_file(sandbox_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(params, handle, indent=2, sort_keys=True)
        logger.debug("Wrote params for sandbox %s", sandbox_id[:8])

    def _read_params(self, sandbox_id: str) -> Dict[str, Any]:
        path = self._param_file(sandbox_id)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                loaded = json.load(handle)
            self._validate_params(loaded)
            return loaded
        return self.default_params.copy()

    # ── Deployment ───────────────────────────────────────

    def deploy(
        self,
        cpu_cores: int = 2,
        memory_mb: int = 2048,
        gpu_passthrough: bool = False,
        network_isolation: bool = True,
        params: Optional[Dict[str, Any]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        model_dir: Optional[str] = None,
    ) -> SandboxState:
        """
        Deploy a new sandboxed engine instance.

        Returns SandboxState with container details.
        """
        if cpu_cores <= 0:
            raise ValueError("cpu_cores must be > 0")
        if memory_mb <= 0:
            raise ValueError("memory_mb must be > 0")

        sandbox_id = str(uuid4())
        merged_params = {**self.default_params, **(params or {})}
        self._validate_params(merged_params)
        self._write_params(sandbox_id, merged_params)

        container_id = ""
        if self._runtime_available:
            container_id = self._launch(
                sandbox_id,
                cpu_cores,
                memory_mb,
                gpu_passthrough,
                network_isolation,
                env_vars,
                model_dir,
            )

        state = SandboxState(
            sandbox_id=sandbox_id,
            container_id=container_id,
            running=bool(container_id),
            parameters=merged_params,
            config_path=self._param_file(sandbox_id),
            last_reconfigured=datetime.now(timezone.utc),
        )
        self._sandboxes[sandbox_id] = state
        logger.info(
            "Sandbox deployed: %s, container=%s, gpu=%s",
            sandbox_id[:8],
            container_id[:12] if container_id else "none",
            gpu_passthrough,
        )
        return state

    def _launch(
        self,
        sandbox_id: str,
        cpu_cores: int,
        memory_mb: int,
        gpu_passthrough: bool,
        network_isolation: bool,
        env_vars: Optional[Dict[str, str]],
        model_dir: Optional[str],
    ) -> str:
        """Build and execute the container run command."""
        container_name = f"s3m-sandbox-{sandbox_id[:8]}"
        param_dir = os.path.join(self.work_dir, sandbox_id)

        cmd = [
            self.runtime,
            "run",
            "-d",
            "--name",
            container_name,
            f"--cpus={cpu_cores}",
            f"--memory={memory_mb}m",
            "-v",
            f"{os.path.abspath(param_dir)}:/opt/s3m/config:rw",
        ]

        if model_dir:
            model_path = Path(model_dir).resolve()
            if not model_path.exists():
                raise ValueError(f"model_dir does not exist: {model_dir}")
            cmd.extend(["-v", f"{model_path}:/opt/s3m/models:ro"])

        if gpu_passthrough:
            cmd.extend(["--gpus", "all"])

        if network_isolation:
            cmd.extend(["--network", "none"])
        else:
            cmd.extend(["--network", "host"])

        if env_vars:
            for key, value in env_vars.items():
                if not key:
                    raise ValueError("env var keys must be non-empty")
                cmd.extend(["-e", f"{key}={value}"])

        cmd.extend(
            [
                "-e",
                f"S3M_SANDBOX_ID={sandbox_id}",
                "-e",
                "S3M_CONFIG_PATH=/opt/s3m/config/params.json",
                self.base_image,
            ]
        )

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return result.stdout.strip()[:64]
            logger.error("Sandbox launch failed: %s", result.stderr.strip())
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.error("Sandbox runtime error: %s", exc)
            return ""

    # ── Parameter Toggling ───────────────────────────────

    def update_params(self, sandbox_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Hot-update parameters for a running sandbox.
        The container watches params.json and applies changes without restart.
        """
        state = self._sandboxes.get(sandbox_id)
        if not state:
            raise ValueError(f"Sandbox {sandbox_id} not found")
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty dict")

        current = self._read_params(sandbox_id)
        candidate = {**current, **updates}
        self._validate_params(candidate)
        self._write_params(sandbox_id, candidate)
        state.parameters = candidate
        state.last_reconfigured = datetime.now(timezone.utc)

        logger.info(
            "Sandbox %s params updated: %s", sandbox_id[:8], sorted(updates.keys())
        )
        return candidate

    def get_params(self, sandbox_id: str) -> Dict[str, Any]:
        return self._read_params(sandbox_id)

    def watch_params(
        self,
        sandbox_id: str,
        on_change: Callable[[Dict[str, Any]], None],
        poll_interval_sec: float = 1.0,
    ) -> bool:
        """
        Watch params.json for changes and invoke callback.

        Uses inotifywait if available, otherwise falls back to mtimes polling.
        """
        if sandbox_id not in self._sandboxes:
            raise ValueError(f"Sandbox {sandbox_id} not found")
        if sandbox_id in self._watchers:
            return True

        stop_event = threading.Event()
        self._watcher_stops[sandbox_id] = stop_event
        path = self._param_file(sandbox_id)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).touch(exist_ok=True)
        self._write_params(sandbox_id, self._read_params(sandbox_id))
        initial_mtime_ns = os.stat(path).st_mtime_ns

        def _watch_loop() -> None:
            inotify = shutil.which("inotifywait")
            if inotify:
                self._watch_with_inotify(
                    inotify=inotify,
                    path=path,
                    stop_event=stop_event,
                    on_change=on_change,
                )
                return
            self._watch_with_polling(
                path=path,
                stop_event=stop_event,
                on_change=on_change,
                poll_interval_sec=poll_interval_sec,
                initial_mtime_ns=initial_mtime_ns,
            )

        thread = threading.Thread(
            target=_watch_loop,
            name=f"s3m-sandbox-watch-{sandbox_id[:8]}",
            daemon=True,
        )
        thread.start()
        self._watchers[sandbox_id] = thread
        return True

    def _watch_with_inotify(
        self,
        inotify: str,
        path: str,
        stop_event: threading.Event,
        on_change: Callable[[Dict[str, Any]], None],
    ) -> None:
        # Tactical context: immediate config uptake allows rapid maneuver
        # between mission modes under adversarial conditions.
        while not stop_event.is_set():
            try:
                result = subprocess.run(
                    [inotify, "-e", "close_write,move,create", path],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if result.returncode == 0:
                    on_change(self._safe_read_params(path))
            except subprocess.TimeoutExpired:
                continue
            except Exception as exc:  # pragma: no cover - defensive path
                logger.error("inotify watcher failed: %s", exc)
                time.sleep(0.5)

    def _watch_with_polling(
        self,
        path: str,
        stop_event: threading.Event,
        on_change: Callable[[Dict[str, Any]], None],
        poll_interval_sec: float,
        initial_mtime_ns: int,
    ) -> None:
        # Capture baseline before thread startup to avoid missing the first write.
        last_mtime_ns = initial_mtime_ns
        while not stop_event.is_set():
            time.sleep(max(0.1, poll_interval_sec))
            try:
                mtime_ns = os.stat(path).st_mtime_ns
            except FileNotFoundError:
                continue
            if mtime_ns != last_mtime_ns:
                last_mtime_ns = mtime_ns
                on_change(self._safe_read_params(path))

    def _safe_read_params(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as handle:
                parsed = json.load(handle)
            self._validate_params(parsed)
            return parsed
        except Exception as exc:
            logger.error("Failed to read watched params file %s: %s", path, exc)
            return {}

    def stop_watch(self, sandbox_id: str) -> bool:
        stop_event = self._watcher_stops.get(sandbox_id)
        watcher = self._watchers.get(sandbox_id)
        if not stop_event or not watcher:
            return False
        stop_event.set()
        watcher.join(timeout=2)
        self._watcher_stops.pop(sandbox_id, None)
        self._watchers.pop(sandbox_id, None)
        return True

    # ── Lifecycle ────────────────────────────────────────

    def stop(self, sandbox_id: str) -> bool:
        """Stop and remove a sandbox container."""
        state = self._sandboxes.get(sandbox_id)
        if not state:
            return False

        self.stop_watch(sandbox_id)

        if state.container_id and self._runtime_available:
            try:
                subprocess.run(
                    [self.runtime, "stop", state.container_id],
                    capture_output=True,
                    timeout=30,
                )
                subprocess.run(
                    [self.runtime, "rm", "-f", state.container_id],
                    capture_output=True,
                    timeout=30,
                )
            except Exception as exc:  # pragma: no cover - defensive path
                logger.error("Failed to stop sandbox %s: %s", sandbox_id[:8], exc)

        state.running = False
        logger.info("Sandbox %s stopped", sandbox_id[:8])
        return True

    def stop_all(self) -> int:
        count = 0
        for sandbox_id in list(self._sandboxes):
            if self.stop(sandbox_id):
                count += 1
        return count

    # ── Logs ─────────────────────────────────────────────

    def get_logs(self, sandbox_id: str, tail: int = 100) -> str:
        """Retrieve recent logs from a sandbox container."""
        if tail <= 0:
            raise ValueError("tail must be > 0")
        state = self._sandboxes.get(sandbox_id)
        if not state or not state.container_id or not self._runtime_available:
            return ""

        try:
            result = subprocess.run(
                [self.runtime, "logs", "--tail", str(tail), state.container_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout + result.stderr
        except Exception:  # pragma: no cover - defensive path
            return ""

    # ── Introspection ────────────────────────────────────

    def list_sandboxes(self) -> List[SandboxState]:
        return list(self._sandboxes.values())

    def health_check(self) -> Dict[str, Any]:
        running = sum(1 for sandbox in self._sandboxes.values() if sandbox.running)
        return {
            "total_sandboxes": len(self._sandboxes),
            "running_sandboxes": running,
            "runtime": self.runtime,
            "runtime_available": self._runtime_available,
            "base_image": self.base_image,
            "watchers_active": len(self._watchers),
        }
