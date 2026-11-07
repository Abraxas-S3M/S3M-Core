"""Fail-closed isolation tests (no Docker required)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from s3m_core.defense.isolation import (
    ContainerManager,
    IsolationUnavailableError,
    SandboxConfig,
    SeccompProfile,
)


def test_production_mode_without_runtime_raises_and_creates_no_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production must refuse session creation when Docker is missing."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    manager = ContainerManager(
        default_config=SandboxConfig(mode="production", runtime="gvisor"),
        seccomp_profile=SeccompProfile(),
    )

    with pytest.raises(IsolationUnavailableError):
        manager.create_session(session_id="prod-no-docker", agent_type="planner")

    assert manager.list_sessions() == []


def test_lab_mode_simulation_sets_flag_and_logs_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Lab mode may simulate but must surface simulation explicitly."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    manager = ContainerManager(
        default_config=SandboxConfig(mode="lab", runtime="gvisor"),
        seccomp_profile=SeccompProfile(),
    )

    with caplog.at_level(logging.WARNING):
        session = manager.create_session(session_id="lab-sim", agent_type="planner")

    assert session.simulated is True
    assert session.container_id.startswith("sim-lab-sim")
    assert any("simulating isolation" in record.message for record in caplog.records)

    report = manager.health_check("lab-sim")
    assert report.details["simulated"] == "true"
    assert report.details["runtime"] == "gvisor"


def test_docker_args_include_hardening_and_never_mount_docker_socket(tmp_path) -> None:
    """Generated docker args must enforce containment defaults."""
    config = SandboxConfig(runtime="gvisor")
    seccomp = tmp_path / "seccomp.json"
    seccomp.write_text("{}", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    args = config.to_docker_args(
        seccomp_profile_path=str(seccomp),
        scratch_mount_src=str(scratch),
    )
    joined = " ".join(args)

    assert "--runtime runsc" in joined or ("--runtime" in args and "runsc" in args)
    assert "--network none" in joined or ("--network" in args and "none" in args)
    assert "--read-only" in args
    assert "--cap-drop ALL" in joined or ("--cap-drop" in args and "ALL" in args)
    assert "no-new-privileges:true" in joined
    assert "--pids-limit" in args
    assert "--memory" in args
    assert "--cpus" in args
    assert f"seccomp={seccomp}" in joined
    assert "/var/run/docker.sock" not in joined


def test_production_docker_start_uses_subprocess_mock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """When Docker exists, session creation must invoke hardened docker run."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[:2] == ["docker", "pull"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:2] == ["docker", "run"]:
            return SimpleNamespace(returncode=0, stdout="real-container-id\n", stderr="")
        if command[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout="4242\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "s3m_core.defense.isolation.container_manager.subprocess.run",
        fake_run,
    )
    root = tmp_path / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    manager = ContainerManager(
        default_config=SandboxConfig(mode="production", runtime="gvisor"),
        seccomp_profile=SeccompProfile(),
    )
    manager._session_storage_root = root

    session = manager.create_session(session_id="hardened", agent_type="planner")
    assert session.simulated is False
    run_cmd = next(cmd for cmd in calls if cmd[:2] == ["docker", "run"])
    joined = " ".join(run_cmd)
    assert "runsc" in joined
    assert "/var/run/docker.sock" not in joined
