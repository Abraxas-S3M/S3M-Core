"""Top-level mission orchestrator with subagent delegation support."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .consensus import MultiAgentConsensus, ValidationResult
from .subagent import PermissionSet, SubAgent, SubAgentResult
from .task_decomposer import SubTask, TaskDecomposer
from .tool_registry import ToolRegistry, ToolResult


@dataclass(slots=True)
class MissionResult:
    """Execution artifact returned after mission completion."""

    objective: str
    plan: Dict[str, Any]
    steps_taken: int
    tools_used: List[str]
    subagents_spawned: int
    results: Dict[str, Any]
    audit_trail: List[Dict[str, Any]]
    sae_alert_log: List[Dict[str, Any]]
    emotion_log: List[Dict[str, Any]]
    time_elapsed: float


@dataclass(slots=True)
class MissionStatus:
    """Snapshot of active orchestration state and subagent progress."""

    objective: Optional[str]
    current_step: int
    total_steps: int
    active_subagents: Dict[str, Dict[str, Any]]
    completed_tasks: List[str]
    pending_tasks: List[str]
    is_complete: bool


class AgenticOrchestrator:
    """
    Top-level agent that decomposes objectives and coordinates subagents.

    Tactical context:
    The orchestrator preserves command intent through long-horizon execution by
    validating delegated work, enforcing permissions, and maintaining audit logs.
    """

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        tool_registry: ToolRegistry,
        action_gate: Any,
        deliberation_gate: Any,
        sae_monitor: Any,
        emotion_probe: Any,
        max_steps: int = 100,
        max_subagents: int = 5,
        context_window: int = 200000,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.tool_registry = tool_registry
        self.action_gate = action_gate
        self.deliberation_gate = deliberation_gate
        self.sae_monitor = sae_monitor
        self.emotion_probe = emotion_probe
        self.max_steps = max_steps
        self.max_subagents = max_subagents
        self.context_window = context_window

        self.decomposer = TaskDecomposer(model=model)
        self.consensus = MultiAgentConsensus()
        self.permission_set = PermissionSet(
            allowed_tools=self.tool_registry.list_tools(),
            allowed_paths=["."],
            network_allowlist=[],
            max_tokens=context_window,
            timeout_seconds=600,
        )

        self._active_subagents: Dict[str, Dict[str, Any]] = {}
        self._subagent_reports: Dict[str, SubAgentResult] = {}
        self._mission_objective: Optional[str] = None
        self._mission_plan: Dict[str, Any] = {}
        self._completed_tasks: set[str] = set()
        self._current_step: int = 0
        self._audit_trail: List[Dict[str, Any]] = []
        self._tools_used: set[str] = set()
        self._sae_alert_log: List[Dict[str, Any]] = []
        self._emotion_log: List[Dict[str, Any]] = []
        self._current_autonomy_level: str = "supervised"

    def execute_mission(
        self,
        objective: str,
        constraints: Optional[List[str]] = None,
        tools_allowed: Optional[List[str]] = None,
        autonomy_level: str = "supervised",
    ) -> MissionResult:
        allowed_levels = {"supervised", "semi_autonomous", "autonomous"}
        if autonomy_level not in allowed_levels:
            raise ValueError(f"autonomy_level must be one of {sorted(allowed_levels)}")

        self._reset_runtime_state(objective=objective, autonomy_level=autonomy_level)
        mission_start = time.monotonic()
        constraints = constraints or []

        plan = self.decomposer.decompose(objective=objective, context="\n".join(constraints))
        self._mission_plan = {
            "tasks": [asdict(task) for task in plan.tasks],
            "dependencies": plan.dependencies,
            "parallelizable_groups": plan.parallelizable_groups,
            "estimated_steps": plan.estimated_steps,
            "estimated_time_seconds": plan.estimated_time_seconds,
        }
        self._record_event("plan_generated", {"task_count": len(plan.tasks), "autonomy_level": autonomy_level})

        task_by_id = {task.task_id: task for task in plan.tasks}
        mission_results: Dict[str, Any] = {}

        for group in plan.parallelizable_groups:
            if self._current_step >= self.max_steps:
                self._record_event("max_steps_reached", {"max_steps": self.max_steps})
                break
            tasks = [task_by_id[task_id] for task_id in group if task_id in task_by_id]
            if len(tasks) > 1:
                group_results = self._execute_parallel_tasks(tasks, tools_allowed=tools_allowed)
                mission_results.update(group_results)
            elif tasks:
                result = self._execute_task_direct(tasks[0], tools_allowed=tools_allowed)
                mission_results[tasks[0].task_id] = result.output
                self._completed_tasks.add(tasks[0].task_id)

        synthesis = self._synthesize_results(objective=objective, mission_results=mission_results)
        mission_results["summary"] = synthesis

        elapsed = time.monotonic() - mission_start
        self._record_event("mission_completed", {"elapsed_seconds": round(elapsed, 3)})
        return MissionResult(
            objective=objective,
            plan=self._mission_plan,
            steps_taken=self._current_step,
            tools_used=sorted(self._tools_used),
            subagents_spawned=len(self._subagent_reports),
            results=mission_results,
            audit_trail=list(self._audit_trail),
            sae_alert_log=list(self._sae_alert_log),
            emotion_log=list(self._emotion_log),
            time_elapsed=elapsed,
        )

    def return_to_human(self, message: str, continue_background: bool = True) -> Dict[str, Any]:
        return {
            "message": message,
            "continue_background": continue_background,
            "active_subagents": dict(self._active_subagents),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_mission_status(self) -> MissionStatus:
        planned_ids = {task["task_id"] for task in self._mission_plan.get("tasks", [])}
        pending = sorted(planned_ids - self._completed_tasks)
        return MissionStatus(
            objective=self._mission_objective,
            current_step=self._current_step,
            total_steps=int(self._mission_plan.get("estimated_steps", 0)),
            active_subagents=dict(self._active_subagents),
            completed_tasks=sorted(self._completed_tasks),
            pending_tasks=pending,
            is_complete=bool(planned_ids) and not pending,
        )

    def invoke_tool(
        self,
        name: str,
        parameters: Dict[str, Any],
        permissions: PermissionSet,
        subagent_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> ToolResult:
        tool_spec = self.tool_registry.get_tool(name)
        action_payload = {
            "tool_name": name,
            "risk_level": tool_spec.risk_level,
            "parameters": dict(parameters),
            "subagent_id": subagent_id,
            "task_id": task_id,
        }
        gate_ok, gate_reason = self._approve_action(action_payload)
        if not gate_ok:
            denial = ToolResult(
                name=name,
                success=False,
                error=f"Action denied: {gate_reason}",
                risk_level=tool_spec.risk_level,
            )
            self._record_event(
                "tool_denied",
                {"tool": name, "reason": denial.error, "subagent_id": subagent_id, "task_id": task_id},
            )
            return denial

        result = self.tool_registry.execute_tool(name=name, parameters=parameters, agent_permissions=permissions)
        self._tools_used.add(name)
        self._current_step += 1
        self._record_event(
            "tool_executed",
            {
                "tool": name,
                "success": result.success,
                "subagent_id": subagent_id,
                "task_id": task_id,
            },
        )
        self._post_tool_checks(result=result, task_id=task_id, subagent_id=subagent_id)
        return result

    def receive_subagent_report(self, agent_id: str, result: SubAgentResult) -> None:
        self._subagent_reports[agent_id] = result
        if agent_id in self._active_subagents:
            self._active_subagents[agent_id]["status"] = "completed"
            self._active_subagents[agent_id]["success"] = result.success
        self._record_event(
            "subagent_report_received",
            {"agent_id": agent_id, "task_id": result.task_id, "success": result.success},
        )

    def _execute_parallel_tasks(
        self,
        tasks: List[SubTask],
        tools_allowed: Optional[List[str]],
    ) -> Dict[str, Any]:
        mission_results: Dict[str, Any] = {}
        for task in tasks[: self.max_subagents]:
            agent_id = f"subagent-{uuid4().hex[:8]}"
            permissions = self._derive_subagent_permissions(task=task, tools_allowed=tools_allowed)
            subagent = SubAgent(
                agent_id=agent_id,
                model=self.model,
                tokenizer=self.tokenizer,
                parent_orchestrator=self,
                task=task,
                tools=list(permissions.allowed_tools),
                permissions=permissions,
            )
            self._active_subagents[agent_id] = {"task_id": task.task_id, "status": "running"}
            result = subagent.execute()
            subagent.report_to_parent(result)
            selected = self._verify_or_retry_subagent_result(task=task, result=result, tools_allowed=tools_allowed)
            mission_results[task.task_id] = selected.output
            self._completed_tasks.add(task.task_id)
        return mission_results

    def _verify_or_retry_subagent_result(
        self,
        *,
        task: SubTask,
        result: SubAgentResult,
        tools_allowed: Optional[List[str]],
    ) -> SubAgentResult:
        validation: ValidationResult = self.consensus.validate_result(
            result=result,
            validation_model=self.model,
            original_task=task,
        )
        self._record_event(
            "subagent_validation",
            {
                "task_id": task.task_id,
                "agent_id": result.agent_id,
                "accepted": validation.accepted,
                "confidence": validation.confidence_score,
                "rationale": validation.rationale,
            },
        )
        if validation.accepted:
            return result

        # Tactical context: skeptical verification forces an independent retry path
        # when delegated output does not pass consistency checks.
        fallback = self._execute_task_direct(task=task, tools_allowed=tools_allowed, verification_retry=True)
        return fallback

    def _execute_task_direct(
        self,
        task: SubTask,
        tools_allowed: Optional[List[str]],
        verification_retry: bool = False,
    ) -> SubAgentResult:
        audit: List[Dict[str, Any]] = [self._event("direct_task_started", {"task_id": task.task_id})]
        outputs: Dict[str, Any] = {}
        for tool_name in task.required_tools:
            if tools_allowed is not None and tool_name not in tools_allowed:
                continue
            result = self.invoke_tool(
                name=tool_name,
                parameters={"task_description": task.description, "retry": verification_retry},
                permissions=self.permission_set,
                task_id=task.task_id,
            )
            outputs[tool_name] = result.output if result.success else {"error": result.error}
            audit.append(self._event("direct_tool", {"tool": tool_name, "success": result.success}))
            if not result.success:
                return SubAgentResult(
                    agent_id="orchestrator",
                    task_id=task.task_id,
                    success=False,
                    output=outputs,
                    tools_used=list(outputs.keys()),
                    audit_trail=audit,
                    error=result.error,
                )

        if not outputs:
            outputs["analysis"] = self._generate_direct_analysis(task.description)
            audit.append(self._event("direct_reasoning", {"task_id": task.task_id}))

        return SubAgentResult(
            agent_id="orchestrator",
            task_id=task.task_id,
            success=True,
            output={"task_description": task.description, "details": outputs},
            tools_used=list(outputs.keys()),
            audit_trail=audit + [self._event("direct_task_completed", {"task_id": task.task_id})],
        )

    def _derive_subagent_permissions(
        self,
        *,
        task: SubTask,
        tools_allowed: Optional[List[str]],
    ) -> PermissionSet:
        allowed_tools = set(self.permission_set.allowed_tools)
        if tools_allowed is not None:
            allowed_tools &= set(tools_allowed)
        required = set(task.required_tools)
        if required:
            allowed_tools &= required
        max_tokens = min(self.permission_set.max_tokens, max(512, task.estimated_complexity * 1024))
        timeout_seconds = min(self.permission_set.timeout_seconds, max(30, task.estimated_complexity * 60))
        return PermissionSet(
            allowed_tools=sorted(allowed_tools),
            allowed_paths=list(self.permission_set.allowed_paths),
            network_allowlist=list(self.permission_set.network_allowlist),
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )

    def _approve_action(self, payload: Dict[str, Any]) -> tuple[bool, str]:
        risk = str(payload.get("risk_level", "low")).lower()
        action_ok, action_reason = self._evaluate_gate(self.action_gate, payload, "action_gate")
        if not action_ok:
            return False, action_reason

        deliberation_ok, deliberation_reason = self._evaluate_gate(
            self.deliberation_gate,
            payload,
            "deliberation_gate",
        )
        if not deliberation_ok:
            return False, deliberation_reason

        if self._current_autonomy_level == "autonomous":
            return True, "autonomous mode"

        if self._current_autonomy_level == "semi_autonomous":
            if "high" in risk and not bool(payload.get("parameters", {}).get("human_approved", False)):
                return False, "high-risk action requires human_approved flag in semi_autonomous mode"
            return True, "semi-autonomous policy"

        if not bool(payload.get("parameters", {}).get("human_approved", False)):
            return False, "supervised mode requires human_approved flag"
        return True, "supervised policy"

    def _evaluate_gate(self, gate: Any, payload: Dict[str, Any], gate_name: str) -> tuple[bool, str]:
        if gate is None:
            return True, f"{gate_name}:not_configured"
        for method_name in ("approve", "evaluate", "check", "assess"):
            method = getattr(gate, method_name, None)
            if not callable(method):
                continue
            try:
                verdict = method(payload)
            except Exception as exc:  # pragma: no cover - defensive behavior
                return False, f"{gate_name} error: {type(exc).__name__}: {exc}"
            return self._normalize_verdict(verdict, gate_name)
        if callable(gate):
            return self._normalize_verdict(gate(payload), gate_name)
        return True, f"{gate_name}:no_callable"

    @staticmethod
    def _normalize_verdict(verdict: Any, gate_name: str) -> tuple[bool, str]:
        if isinstance(verdict, bool):
            return verdict, f"{gate_name}:{'approved' if verdict else 'rejected'}"
        if isinstance(verdict, dict):
            approved = bool(verdict.get("approved", verdict.get("allow", False)))
            reason = str(verdict.get("reason", gate_name))
            return approved, reason
        return bool(verdict), f"{gate_name}:cast_bool"

    def _post_tool_checks(
        self,
        *,
        result: ToolResult,
        task_id: Optional[str],
        subagent_id: Optional[str],
    ) -> None:
        alert = self._safe_monitor_call(self.sae_monitor, result=result, task_id=task_id, subagent_id=subagent_id)
        if alert is not None:
            self._sae_alert_log.append(alert)
            self._record_event("sae_alert", {"task_id": task_id, "subagent_id": subagent_id, "alert": alert})

        emotion = self._safe_emotion_call(self.emotion_probe, result=result, task_id=task_id, subagent_id=subagent_id)
        if emotion is not None:
            self._emotion_log.append(emotion)
            self._record_event(
                "emotion_profile_updated",
                {"task_id": task_id, "subagent_id": subagent_id, "emotion": emotion},
            )

    @staticmethod
    def _safe_monitor_call(monitor: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if monitor is None:
            return None
        for method_name in ("check_alerts", "inspect", "evaluate"):
            method = getattr(monitor, method_name, None)
            if not callable(method):
                continue
            try:
                output = method(**kwargs)
            except TypeError:
                output = method(kwargs)
            if output:
                return output if isinstance(output, dict) else {"alert": output}
        return None

    @staticmethod
    def _safe_emotion_call(probe: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if probe is None:
            return None
        for method_name in ("profile", "probe", "evaluate"):
            method = getattr(probe, method_name, None)
            if not callable(method):
                continue
            try:
                output = method(**kwargs)
            except TypeError:
                output = method(kwargs)
            if output:
                return output if isinstance(output, dict) else {"state": output}
        return None

    def _synthesize_results(self, objective: str, mission_results: Dict[str, Any]) -> str:
        synthesize = getattr(self.model, "synthesize", None)
        if callable(synthesize):
            try:
                return str(synthesize(objective=objective, results=mission_results))
            except Exception:
                pass
        completed = len([key for key in mission_results.keys() if key != "summary"])
        return f"Mission objective processed. Completed task results: {completed}."

    def _generate_direct_analysis(self, task_description: str) -> str:
        generator = getattr(self.model, "generate", None)
        if callable(generator):
            try:
                return str(generator(task_description))
            except Exception:
                pass
        return f"Direct analysis completed for task: {task_description}"

    def _reset_runtime_state(self, *, objective: str, autonomy_level: str) -> None:
        self._mission_objective = objective
        self._current_autonomy_level = autonomy_level
        self._active_subagents.clear()
        self._subagent_reports.clear()
        self._completed_tasks.clear()
        self._current_step = 0
        self._audit_trail.clear()
        self._tools_used.clear()
        self._sae_alert_log.clear()
        self._emotion_log.clear()

    def _record_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        self._audit_trail.append(self._event(event_type, payload))

    @staticmethod
    def _event(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": event_type,
            "payload": dict(payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
