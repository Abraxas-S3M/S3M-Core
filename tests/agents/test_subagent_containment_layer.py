"""Unit tests for subagent containment defenses in S3M."""

from __future__ import annotations

from pathlib import Path

from s3m_core.agents.subagent import PermissionSet
from s3m_core.defense.subagent import (
    AgentInfo,
    KeystrokeSimulationDetector,
    PermissionInheritance,
    SpawnGate,
    SpawnRequest,
)


def _parent_permissions() -> PermissionSet:
    return PermissionSet(
        allowed_tools=["file_read", "spawn_subagent_grant", "bash_execute"],
        allowed_paths=["/workspace"],
        network_allowlist=["local.mesh"],
        max_tokens=4096,
        timeout_seconds=300,
    )


def test_compute_child_permissions_uses_intersection_and_minimums() -> None:
    inheritance = PermissionInheritance()
    child = inheritance.compute_child_permissions(
        parent=_parent_permissions(),
        requested=PermissionSet(
            allowed_tools=["file_read", "file_write"],
            allowed_paths=["/workspace/sector-a", "/tmp"],
            network_allowlist=["local.mesh", "internet.local"],
            max_tokens=8192,
            timeout_seconds=120,
        ),
    )

    assert child.allowed_tools == ["file_read"]
    assert child.allowed_paths == ["/workspace/sector-a"]
    assert child.network_allowlist == ["local.mesh"]
    assert child.max_tokens == 4096
    assert child.timeout_seconds == 120


def test_validate_hierarchy_reports_permission_escalation() -> None:
    inheritance = PermissionInheritance()
    violations = inheritance.validate_hierarchy(
        [
            AgentInfo(agent_id="parent", parent_id=None, permissions=_parent_permissions()),
            AgentInfo(
                agent_id="child",
                parent_id="parent",
                permissions=PermissionSet(
                    allowed_tools=["file_read", "file_write"],
                    allowed_paths=["/workspace"],
                    network_allowlist=["local.mesh"],
                    max_tokens=5000,
                    timeout_seconds=300,
                ),
            ),
        ]
    )

    violation_names = {item.permission for item in violations}
    assert "allowed_tools" in violation_names
    assert "max_tokens" in violation_names


def test_spawn_gate_denies_tmux_new_session() -> None:
    alerts: list[dict] = []
    gate = SpawnGate(
        parent_permission_lookup=lambda _session: _parent_permissions(),
        alert_sink=alerts.append,
    )

    decision = gate.evaluate_spawn(
        "parent-session-1",
        SpawnRequest(
            command="tmux new-session -s rogue",
            requested_permissions=_parent_permissions(),
            spawn_type="tmux",
            justification="run detached helper",
        ),
    )

    assert not decision.approved
    assert "Mythos attack vector" in decision.reason
    assert alerts and alerts[-1]["level"] == "critical"


def test_spawn_gate_requires_explicit_subagent_grant() -> None:
    gate = SpawnGate(
        parent_permission_lookup=lambda _session: PermissionSet(
            allowed_tools=["file_read"],
            allowed_paths=["/workspace"],
            network_allowlist=[],
            max_tokens=2048,
            timeout_seconds=120,
        )
    )
    decision = gate.evaluate_spawn(
        "parent-session-2",
        SpawnRequest(
            command="spawn_worker",
            requested_permissions=PermissionSet(
                allowed_tools=["file_read"],
                allowed_paths=["/workspace"],
                network_allowlist=[],
                max_tokens=1024,
                timeout_seconds=60,
            ),
            spawn_type="subagent",
            justification="delegate parsing work",
        ),
    )
    assert not decision.approved
    assert "explicit subagent spawn grant" in decision.reason


def test_spawn_gate_allows_background_spawn_with_monitoring() -> None:
    gate = SpawnGate(parent_permission_lookup=lambda _session: _parent_permissions())
    decision = gate.evaluate_spawn(
        "parent-session-3",
        SpawnRequest(
            command="python worker.py &",
            requested_permissions=PermissionSet(
                allowed_tools=["file_read"],
                allowed_paths=["/workspace/sector-a"],
                network_allowlist=[],
                max_tokens=1024,
                timeout_seconds=90,
            ),
            spawn_type="bg",
            justification="keep telemetry parser running in background",
        ),
    )
    assert decision.approved
    assert decision.container_config.monitor_background is True
    assert decision.actual_permissions.allowed_tools == ["file_read"]


def test_keystroke_detector_blocks_and_kills_offending_process(tmp_path: Path) -> None:
    blocked: list[tuple[str, str, str]] = []
    killed: list[int] = []
    alerts: list[dict] = []

    class GateStub:
        def block_command(self, *, session_id: str, command: str, reason: str) -> None:
            blocked.append((session_id, command, reason))

    detector = KeystrokeSimulationDetector(
        execution_gate=GateStub(),
        command_source=lambda _session: [
            {
                "command": "tmux send-keys -t session:0.0 'y' C-m",
                "pid": 4321,
                "cwd": str(tmp_path),
            }
        ],
        process_killer=lambda pid: killed.append(pid),
        alert_sink=alerts.append,
    )
    detector.monitor_for_simulation("session-x")

    assert len(detector.detections) == 1
    assert blocked and blocked[0][0] == "session-x"
    assert killed == [4321]
    assert alerts and alerts[0]["level"] == "critical"


def test_keystroke_detector_flags_script_with_prompt_and_autoapprove(tmp_path: Path) -> None:
    script_path = tmp_path / "autoapprove.sh"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'echo "Approve this command? [y/N]"',
                "yes | secure_command --requires-approval",
            ]
        ),
        encoding="utf-8",
    )
    alerts: list[dict] = []

    class GateStub:
        def block_command(self, *, session_id: str, command: str, reason: str) -> None:  # noqa: ARG002
            return None

    detector = KeystrokeSimulationDetector(
        execution_gate=GateStub(),
        command_source=lambda _session: [{"command": f"bash {script_path}", "cwd": str(tmp_path)}],
        alert_sink=alerts.append,
    )
    detector.monitor_for_simulation("session-script")

    assert len(detector.detections) == 1
    assert "permission-prompt automation markers" in detector.detections[0].reason
    assert alerts and alerts[0]["event_type"] == "keystroke_simulation_detected"
