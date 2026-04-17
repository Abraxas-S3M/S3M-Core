"""Unit tests for s3m_core agentic orchestration modules."""

import sys

import pytest

sys.path.insert(0, ".")

from s3m_core.agents import (  # noqa: E402
    AgenticOrchestrator,
    PermissionSet,
    SubAgent,
    SubTask,
    TaskDecomposer,
    ToolRegistry,
)


class AlwaysApproveGate:
    def approve(self, _: dict) -> bool:
        return True


class StaticModel:
    def decompose(self, objective: str, context: str | None = None) -> dict:  # noqa: ARG002
        return {
            "tasks": [
                {
                    "task_id": "collect",
                    "description": f"Collect intel for {objective}",
                    "required_tools": ["intel_lookup"],
                    "estimated_complexity": 1,
                    "can_parallelize": True,
                    "depends_on": [],
                },
                {
                    "task_id": "assess",
                    "description": "Assess force posture",
                    "required_tools": ["intel_lookup"],
                    "estimated_complexity": 1,
                    "can_parallelize": True,
                    "depends_on": [],
                },
            ]
        }

    def validate_result(self, result, task) -> dict:  # noqa: ANN001, ANN201
        return {
            "addresses_task": False,
            "internally_consistent": bool(result.success),
            "conflicts": False,
            "confidence_score": 0.3,
            "rationale": f"force independent verification for {task.task_id}",
        }


class PassiveSAEMonitor:
    def check_alerts(self, **kwargs):  # noqa: ANN003, ANN201
        if not kwargs["result"].success:
            return {"severity": "high", "message": "tool failed"}
        return None


class PassiveEmotionProbe:
    def profile(self, **kwargs):  # noqa: ANN003, ANN201
        return {"state": "calm", "task_id": kwargs.get("task_id")}


def test_task_decomposer_rejects_cycles():
    class CyclicModel:
        def decompose(self, objective: str, context: str | None = None) -> dict:  # noqa: ARG002
            return {
                "tasks": [
                    {
                        "task_id": "t1",
                        "description": "first",
                        "required_tools": [],
                        "estimated_complexity": 1,
                        "can_parallelize": False,
                        "depends_on": ["t2"],
                    },
                    {
                        "task_id": "t2",
                        "description": "second",
                        "required_tools": [],
                        "estimated_complexity": 1,
                        "can_parallelize": False,
                        "depends_on": ["t1"],
                    },
                ]
            }

    decomposer = TaskDecomposer(model=CyclicModel())
    with pytest.raises(ValueError, match="cycle"):
        decomposer.decompose("validate route graph")


def test_subagent_permissions_cannot_escalate():
    class DummyParent:
        permission_set = PermissionSet(
            allowed_tools=["file_read"],
            allowed_paths=["/workspace"],
            network_allowlist=["example.local"],
            max_tokens=1024,
            timeout_seconds=120,
        )

    with pytest.raises(ValueError, match="restrictive"):
        SubAgent(
            agent_id="a1",
            model=None,
            tokenizer=None,
            parent_orchestrator=DummyParent(),
            task=SubTask(task_id="x", description="x"),
            tools=["file_read", "file_write"],
            permissions=PermissionSet(
                allowed_tools=["file_read", "file_write"],
                allowed_paths=["/workspace"],
                network_allowlist=["example.local"],
                max_tokens=2048,
                timeout_seconds=300,
            ),
        )


def test_tool_registry_enforces_tool_permissions():
    registry = ToolRegistry()
    deny_permissions = PermissionSet(allowed_tools=["file_read"], allowed_paths=["."], network_allowlist=[])
    result = registry.execute_tool(
        name="file_delete",
        parameters={"path": "/tmp/forbidden"},
        agent_permissions=deny_permissions,
    )
    assert not result.success
    assert "not allowed" in (result.error or "")


def test_orchestrator_executes_parallel_tasks_with_skepticism_retry():
    registry = ToolRegistry()
    registry.register_tool(
        name="intel_lookup",
        handler=lambda params: {"intel": params["task_description"], "confidence": 0.88},
        risk_level="low",
        description="Lookup local tactical intel cache",
        parameter_schema={"task_description": "str"},
    )
    orchestrator = AgenticOrchestrator(
        model=StaticModel(),
        tokenizer=None,
        tool_registry=registry,
        action_gate=AlwaysApproveGate(),
        deliberation_gate=AlwaysApproveGate(),
        sae_monitor=PassiveSAEMonitor(),
        emotion_probe=PassiveEmotionProbe(),
        max_steps=20,
        max_subagents=4,
    )

    result = orchestrator.execute_mission(
        objective="build coordinated patrol recommendation",
        autonomy_level="autonomous",
        constraints=["no network usage", "offline-only"],
    )

    assert "collect" in result.results
    assert "assess" in result.results
    assert result.subagents_spawned == 2
    assert any(event["event_type"] == "subagent_validation" for event in result.audit_trail)
    assert len(result.emotion_log) >= 2

    status = orchestrator.get_mission_status()
    assert status.is_complete
    handoff = orchestrator.return_to_human("Mission stable", continue_background=True)
    assert handoff["continue_background"] is True
