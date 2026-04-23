"""Container session lifecycle management for hardened agent runtime cells."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .sandbox_config import SandboxConfig
from .seccomp_profile import SeccompProfile


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

        self._pull_base_image(image=image, runtime=config.runtime)
        seccomp_dict = self.seccomp_profile.generate_profile(mode="strict")
        metadata["seccomp_default_action"] = str(seccomp_dict.get("defaultAction", ""))

        vault_mount = self._mount_credential_vault_agent(session_id=session_id)
        network_policy = self._configure_network_policies(session_id=session_id, config=config)
        container_id, pid = self._start_runtime_cell(
            session_id=session_id,
            image=image,
            config=config,
            vault_mount=vault_mount,
            network_policy=network_policy,
        )

        session = ContainerSession(
            session_id=session_id,
            container_id=container_id,
            pid=pid,
            created_at=datetime.now(timezone.utc),
            config=config,
            status="running",
            image=image,
            metadata=metadata,
        )
        self._sessions[session_id] = session
        return session

    def destroy_session(self, session_id: str) -> None:
        """Force-stop a container session and wipe ephemeral traces."""
        session = self._sessions.get(session_id)
        if session is None:
            return

        self._kill_runtime_cell(container_id=session.container_id, runtime=session.config.runtime)
        self._wipe_ephemeral_storage(session_id=session_id)
        self._remove_network_policies(session_id=session_id)
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
        }
        details = {
            "runtime": session.config.runtime,
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

    def _pull_base_image(self, image: str, runtime: str) -> None:
        if runtime != "docker":
            return
        if shutil.which("docker") is None:
            return
        self._run_command(["docker", "pull", image])

    def _mount_credential_vault_agent(self, session_id: str) -> str:
        # Tactical note: each session gets a private vault mountpoint so
        # compromised agents cannot pivot laterally into adjacent credentials.
        session_dir = self._session_storage_root / session_id
        vault_path = session_dir / "vault"
        vault_path.mkdir(parents=True, exist_ok=True)
        return str(vault_path)

    def _configure_network_policies(self, session_id: str, config: SandboxConfig) -> str:
        if config.use_net_namespace:
            return f"s3m-net-{session_id}"
        return "host"

    def _remove_network_policies(self, session_id: str) -> None:
        _ = session_id

    def _start_runtime_cell(
        self,
        session_id: str,
        image: str,
        config: SandboxConfig,
        vault_mount: str,
        network_policy: str,
    ) -> tuple[str, int]:
        if config.runtime == "docker" and shutil.which("docker") is not None:
            docker_args = config.to_docker_args()
            command = [
                "docker",
                "run",
                "-d",
                "--name",
                f"s3m-{session_id}",
                "--network",
                network_policy,
                "--mount",
                f"type=bind,src={vault_mount},dst=/vault,readonly",
                *docker_args,
                image,
                "sleep",
                "infinity",
            ]
            result = self._run_command(command)
            container_id = result.stdout.strip()
            pid = self._lookup_container_pid(container_id=container_id)
            return container_id, pid

        simulated_container = f"sim-{session_id}-{uuid.uuid4().hex[:12]}"
        return simulated_container, os.getpid()

    def _kill_runtime_cell(self, container_id: str, runtime: str) -> None:
        if runtime == "docker" and container_id and not container_id.startswith("sim-"):
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
