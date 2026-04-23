"""Unit tests for the S3M process isolation defensive hardening layer."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from s3m_core.defense.isolation import (
    ContainerManager,
    ProcGuard,
    SandboxConfig,
    SeccompProfile,
)


def test_sandbox_config_generates_hardened_docker_args() -> None:
    """Docker arguments should include core namespace and /proc hardening controls."""
    config = SandboxConfig()
    args = config.to_docker_args()

    assert "--pid=private" in args
    assert "--network=bridge" in args
    assert "--cap-drop=SYS_PTRACE" in args
    assert "s3m.masked_proc_paths=" in " ".join(args)
    assert "--memory" in args


def test_sandbox_config_validate_flags_weak_controls() -> None:
    """Validation should emit warnings for known isolation weaknesses."""
    config = SandboxConfig(
        runtime="docker",
        use_pid_namespace=False,
        mount_proc_readonly=False,
        allowed_devices=["/dev/null", "/dev/mem"],
        mask_proc_paths=["/proc/*/status"],
    )
    warnings = config.validate()

    assert any("minimum viable isolation" in warning for warning in warnings)
    assert any("PID namespace is disabled" in warning for warning in warnings)
    assert any("writable" in warning for warning in warnings)
    assert any("Dangerous device nodes exposed" in warning for warning in warnings)
    assert any("Critical /proc mask entries missing" in warning for warning in warnings)


def test_seccomp_profile_strict_contains_required_blocks_and_allows() -> None:
    """Strict profile should enforce deny-by-default with key syscall controls."""
    profile = SeccompProfile()
    generated = profile.generate_profile(mode="strict")
    syscalls = generated["syscalls"]

    assert generated["defaultAction"] == "SCMP_ACT_ERRNO"
    assert any("ptrace" in entry["names"] for entry in syscalls)
    assert any("process_vm_readv" in entry["names"] for entry in syscalls)
    assert any("read" in entry["names"] for entry in syscalls)
    assert any("clock_gettime" in entry["names"] for entry in syscalls)

    rendered = profile.to_json()
    decoded = json.loads(rendered)
    assert decoded["defaultAction"] == "SCMP_ACT_ERRNO"


def test_seccomp_install_requires_current_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install path should reject non-local PID and use prctl for local PID."""
    profile = SeccompProfile(mode="standard")
    with pytest.raises(PermissionError):
        profile.install_for_process(pid=os.getpid() + 1)

    profile.generate_profile(mode="strict")
    calls: list[tuple[int, int]] = []

    class DummyLib:
        def prctl(self, command: int, arg2: int, _arg3: int, _arg4: int, _arg5: int) -> int:
            calls.append((command, arg2))
            return 0

    monkeypatch.setattr("ctypes.CDLL", lambda *_args, **_kwargs: DummyLib())
    profile.install_for_process(pid=os.getpid())
    assert (38, 1) in calls
    assert (22, 1) in calls


def test_container_manager_session_lifecycle_and_health() -> None:
    """Manager should create, report, and destroy simulated isolation sessions."""
    config = SandboxConfig(runtime="gvisor")
    manager = ContainerManager(default_config=config, seccomp_profile=SeccompProfile())

    session = manager.create_session(session_id="alpha-session", agent_type="planner")
    assert session.session_id == "alpha-session"
    assert session.container_id.startswith("sim-alpha-session")
    assert len(manager.list_sessions()) == 1

    report = manager.health_check("alpha-session")
    assert report.healthy is True
    assert report.checks["proc_readonly"] is True
    assert report.checks["seccomp_active"] is True

    manager.destroy_session("alpha-session")
    assert manager.list_sessions() == []


def test_proc_guard_alert_modes_and_time_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProcGuard should record and filter alerts with mode-specific actions."""
    guard = ProcGuard()
    monkeypatch.setattr("shutil.which", lambda _binary: None)
    guard.install(container_id="cont-1")
    assert len(guard.get_alerts()) == 1

    guard.set_response_mode("block")
    first = guard.record_attempt(
        pid=777,
        syscall="openat",
        target_path="/proc/1/environ",
        calling_binary="/usr/bin/python",
    )
    assert first.action_taken == "blocked"

    guard.set_response_mode("kill")
    second = guard.record_attempt(
        pid=888,
        syscall="ptrace",
        target_path="/proc/2/mem",
        calling_binary="/usr/bin/gdb",
    )
    assert second.action_taken == "killed"

    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert guard.get_alerts(since=future) == []
