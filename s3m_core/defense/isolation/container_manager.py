"""Container session lifecycle management for hardened agent runtime cells."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .exceptions import IsolationUnavailableError
from .firecracker_runtime import FirecrackerRuntime
from .sandbox_config import SandboxConfig
from .seccomp_profile import SeccompProfile

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ContainerSession:
    """Runtime handle for one isolated agent container session."""

    session_id: str
    container_id: str
    pid: int
    created_at: datetime
    config: SandboxConfig
    status: str
    image: str
    simulated: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class HealthReport:
    """Health and integrity status for an active container session."""

    session_id: str
    healthy: bool
    checks: Dict[str, bool]
    details: Dict[str, str]
    checked_at: datetime


class ContainerManager:
    """
    Creates and destroys isolated container sessions for agent workloads.

    Tactical context:
    Container sessions are disposable defensive enclaves that constrain
    autonomous agents to a bounded blast radius during contested operations.
    """

    def __init__(
        self,
        default_config: SandboxConfig,
        seccomp_profile: SeccompProfile,
        image_registry: str = "s3m-registry.local",
    ) -> None:
        self.default_config = default_config
        self.seccomp_profile = seccomp_profile
        self.image_registry = image_registry.rstrip("/")
        self._sessions: Dict[str, ContainerSession] = {}
        self._session_storage_root = Path("/tmp/s3m-isolation-sessions")
        self._session_storage_root.mkdir(parents=True, exist_ok=True)
        self._firecracker = FirecrackerRuntime()

    def create_session(
        self,
        session_id: str,
        agent_type: str,
        config_override: Optional[SandboxConfig] = None,
    ) -> ContainerSession:
        """Create a new isolated container session and return its handle."""
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}", session_id):
            raise ValueError("session_id must be 3-64 chars and use [A-Za-z0-9_.-].")
        if session_id in self._sessions:
            raise ValueError(f"Session '{session_id}' already exists.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}", agent_type):
            raise ValueError("agent_type must be lowercase and use [a-z0-9_.-].")

        config = config_override or self.default_config
        image = f"{self.image_registry}/{agent_type}:latest"

        warnings = config.validate()
        metadata: Dict[str, str] = {}
        if warnings:
            metadata["config_warnings"] = " | ".join(warnings)

        network_mode = config.resolved_network_mode()
        metadata["network_mode"] = network_mode

        seccomp_dict = self.seccomp_profile.generate_profile(mode="strict")
        metadata["seccomp_default_action"] = str(seccomp_dict.get("defaultAction", ""))

        simulated = False
        if config.runtime == "firecracker":
            scratch_mount, seccomp_path = self._prepare_session_artifacts(session_id=session_id)
            metadata["seccomp_profile_path"] = seccomp_path
            container_id, pid = self._firecracker.start_session_cell(
                session_id=session_id,
                image=image,
                config=config,
                scratch_mount=scratch_mount,
                network_mode=network_mode,
                extra_args=config.to_docker_args(
                    seccomp_profile_path=seccomp_path,
                    scratch_mount_src=scratch_mount,
                ),
            )
        elif self._docker_runtime_available():
            self._pull_base_image(image=image)
            scratch_mount, seccomp_path = self._prepare_session_artifacts(session_id=session_id)
            metadata["seccomp_profile_path"] = seccomp_path
            container_id, pid = self._start_docker_cell(
                session_id=session_id,
                image=image,
                config=config,
                scratch_mount=scratch_mount,
                seccomp_path=seccomp_path,
            )
        elif config.mode == "production":
            raise IsolationUnavailableError(
                "Production sandbox mode requires Docker (gVisor runsc or plain docker) "
                "but no runtime binary was found on PATH."
            )
        else:
            logger.warning(
                "Lab mode: Docker unavailable; simulating isolation for session '%s'.",
                session_id,
            )
            container_id = f"sim-{session_id}-{uuid.uuid4().hex[:12]}"
            pid = os.getpid()
            simulated = True
            metadata["simulated"] = "true"

        session = ContainerSession(
            session_id=session_id,
            container_id=container_id,
            pid=pid,
            created_at=datetime.now(timezone.utc),
            config=config,
            status="running",
            image=image,
            simulated=simulated,
            metadata=metadata,
        )
        self._sessions[session_id] = session
        return session

    def destroy_session(self, session_id: str) -> None:
        """Force-stop a container session and wipe ephemeral traces."""
        session = self._sessions.get(session_id)
        if session is None:
            return

        if not session.simulated:
            self._kill_runtime_cell(container_id=session.container_id)
        self._wipe_ephemeral_storage(session_id=session_id)
        session.status = "destroyed"
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> List[ContainerSession]:
        """List active sessions in deterministic creation order."""
        return sorted(self._sessions.values(), key=lambda item: item.created_at)

    def health_check(self, session_id: str) -> HealthReport:
        """
        Verify namespace, seccomp, and resource-limit controls remain active.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown session '{session_id}'.")

        checks = {
            "pid_namespace": session.config.use_pid_namespace,
            "net_namespace": session.config.use_net_namespace,
            "mount_namespace": session.config.use_mount_namespace,
            "user_namespace": session.config.use_user_namespace,
            "proc_readonly": session.config.mount_proc_readonly,
            "hide_other_pids": session.config.hide_other_pids,
            "seccomp_active": bool(session.metadata.get("seccomp_default_action")),
            "resource_limits_applied": all(
                [
                    session.config.max_memory_mb > 0,
                    0 < session.config.max_cpu_percent <= 100,
                    session.config.max_open_files > 0,
                    session.config.max_processes > 0,
                    session.config.max_file_size_mb > 0,
                ]
            ),
            "not_simulated_in_production": not (
                session.config.mode == "production" and session.simulated
            ),
        }
        network_mode = session.metadata.get(
            "network_mode",
            session.config.resolved_network_mode(),
        )
        details = {
            "runtime": session.config.runtime,
            "network_mode": network_mode,
            "simulated": str(session.simulated).lower(),
            "sandbox_mode": session.config.mode,
            "container_id": session.container_id,
            "status": session.status,
            "warnings": session.metadata.get("config_warnings", ""),
        }
        healthy = all(checks.values()) and session.status == "running"
        return HealthReport(
            session_id=session_id,
            healthy=healthy,
            checks=checks,
            details=details,
            checked_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _docker_runtime_available() -> bool:
        return shutil.which("docker") is not None

    def _pull_base_image(self, image: str) -> None:
        if shutil.which("docker") is None:
            return
        self._run_command(["docker", "pull", image])

    def _prepare_session_artifacts(self, *, session_id: str) -> tuple[str, str]:
        session_dir = self._session_storage_root / session_id
        scratch_path = session_dir / "scratch"
        scratch_path.mkdir(parents=True, exist_ok=True)
        vault_path = session_dir / "vault"
        vault_path.mkdir(parents=True, exist_ok=True)

        seccomp_path = session_dir / "seccomp.json"
        profile = self.seccomp_profile.generate_profile(mode="strict")
        seccomp_path.write_text(json.dumps(profile), encoding="utf-8")

        return str(scratch_path), str(seccomp_path)

    def _start_docker_cell(
        self,
        *,
        session_id: str,
        image: str,
        config: SandboxConfig,
        scratch_mount: str,
        seccomp_path: str,
    ) -> tuple[str, int]:
        docker_args = config.to_docker_args(
            seccomp_profile_path=seccomp_path,
            scratch_mount_src=scratch_mount,
        )
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            f"s3m-{session_id}",
            *docker_args,
            image,
            "sleep",
            "infinity",
        ]
        result = self._run_command(command)
        container_id = result.stdout.strip()
        pid = self._lookup_container_pid(container_id=container_id)
        return container_id, pid

    def _kill_runtime_cell(self, container_id: str) -> None:
        if container_id and not container_id.startswith("sim-"):
            if shutil.which("docker") is None:
                return
            self._run_command(["docker", "rm", "-f", container_id], check=False)

    def _wipe_ephemeral_storage(self, session_id: str) -> None:
        session_dir = self._session_storage_root / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def _lookup_container_pid(self, container_id: str) -> int:
        if not container_id:
            return -1
        if shutil.which("docker") is None:
            return -1
        result = self._run_command(
            ["docker", "inspect", "--format", "{{.State.Pid}}", container_id],
            check=False,
        )
        if result.returncode != 0:
            return -1
        try:
            return int(result.stdout.strip())
        except ValueError:
            return -1

    @staticmethod
    def _run_command(command: List[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, check=check, capture_output=True, text=True)
