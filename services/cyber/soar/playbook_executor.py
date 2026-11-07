"""Execution runtime for SOC SOAR playbooks."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from services.cyber.config import soar_auto_execute
from services.cyber.ir_platforms.ir_bridge import IRPlatformBridge
from services.cyber.models import (
    CaseStatus,
    IncidentCase,
    Playbook,
    PlaybookAction,
    PlaybookStatus,
    PlaybookStep,
    PlaybookStepKind,
)
from services.cyber.soar.step_classification import (
    classify_playbook_step,
    forbidden_playbook_actions,
    is_forbidden_action,
    resolve_tool_name,
)
from src.cortex.policy_gate import Approvals, MissionEnvelope, PolicyGate, ToolCall, evaluate_soar_tool_call
from src.security.crypto.secure_audit_log import SecureAuditLog


class PlaybookExecutor:
    """Executes tactical SOC playbook steps with defensive failure handling."""

    def __init__(
        self,
        ir_bridge: object = None,
        *,
        auto_execute: Optional[bool] = None,
        audit_log: Optional[SecureAuditLog] = None,
    ) -> None:
        self.ir_bridge = ir_bridge if ir_bridge is not None else IRPlatformBridge()
        self.auto_execute = soar_auto_execute() if auto_execute is None else bool(auto_execute)
        self.audit_log = audit_log
        self._history: List[dict] = []
        self._approval_queue: List[dict] = []
        self._executed_mutations: Set[Tuple[str, int, str]] = set()

    def _severity_rank(self, severity: str) -> int:
        mapping = {"INFORMATIONAL": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}
        return mapping.get(severity.upper(), 0)

    def _evaluate_condition(self, condition: str, case: IncidentCase, context: dict) -> bool:
        if not condition:
            return True
        expr = condition.strip()
        if not expr:
            return True
        if expr.startswith("severity >="):
            target = expr.split(">=", 1)[1].strip().upper()
            return self._severity_rank(case.severity.value) >= self._severity_rank(target)
        if expr.startswith("enrichment_verdict =="):
            target = expr.split("==", 1)[1].strip().lower()
            return str(context.get("enrichment_verdict", "unknown")).lower() == target
        if expr.startswith("enrichment_verdict !="):
            target = expr.split("!=", 1)[1].strip().lower()
            return str(context.get("enrichment_verdict", "unknown")).lower() != target
        return False

    def _step_kind(self, step: PlaybookStep) -> PlaybookStepKind:
        if step.step_kind is not None:
            return step.step_kind
        return classify_playbook_step(
            step.action,
            parameters=step.parameters,
            step_name=step.name,
        )

    def _record_policy_decision(
        self,
        case: IncidentCase,
        step: PlaybookStep,
        decision_dict: dict,
    ) -> None:
        detail = (
            f"step={step.step_id} action={step.action.value} "
            f"outcome={decision_dict.get('outcome')} reason={decision_dict.get('reason')}"
        )
        case.add_timeline_entry("policy_gate_decision", "cortex_policy_gate", detail)
        if self.audit_log is not None:
            self.audit_log.log(
                "soar_policy_gate",
                {
                    "case_id": case.case_id,
                    "step_id": step.step_id,
                    "action": step.action.value,
                    "decision": decision_dict,
                },
                severity="INFO",
                source="soar_playbook_executor",
            )

    def _queue_mutate_step(
        self,
        step: PlaybookStep,
        case: IncidentCase,
        decision_dict: dict,
        started: float,
    ) -> dict:
        step.status = PlaybookStatus.ABORTED
        payload = {
            "step_id": step.step_id,
            "action": step.action.value,
            "status": "awaiting_approval",
            "output": {
                "reason": decision_dict.get("reason", "awaiting_approval"),
                "policy_decision": decision_dict,
            },
            "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
        }
        queue_entry = {
            "case_id": case.case_id,
            "step_id": step.step_id,
            "action": step.action.value,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "policy_decision": decision_dict,
        }
        self._approval_queue.append(queue_entry)
        case.add_timeline_entry(
            "mutate_step_queued",
            "soar_executor",
            f"Awaiting approval for {step.action.value}",
        )
        return payload

    def _run_step_body(self, step: PlaybookStep, case: IncidentCase, context: dict) -> Dict[str, Any]:
        action = step.action
        output: Dict[str, Any] = {}
        if action == PlaybookAction.BLOCK_IP:
            output = {"message": "Block IP action logged", "parameters": dict(step.parameters)}
        elif action == PlaybookAction.ISOLATE_HOST:
            output = {"message": "Host isolation command logged", "parameters": dict(step.parameters)}
        elif action == PlaybookAction.DISABLE_ACCOUNT:
            output = {"message": "Account disable request logged", "parameters": dict(step.parameters)}
        elif action == PlaybookAction.SCAN_ENDPOINT:
            output = {"message": "Endpoint scan request logged", "parameters": dict(step.parameters)}
        elif action == PlaybookAction.COLLECT_FORENSICS:
            dfir = self.ir_bridge.dfir_iris.add_evidence(
                case.case_id,
                {"type": "forensic_task", "artifacts": step.parameters.get("artifacts", [])},
            )
            output = {"message": "Forensic collection task issued", "dfir": dfir}
        elif action == PlaybookAction.NOTIFY_ANALYST:
            queue = context.setdefault("analyst_alerts", [])
            queue.append(
                {
                    "case_id": case.case_id,
                    "priority": step.parameters.get("priority", "normal"),
                    "channel": step.parameters.get("channel", "soc_alerts"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            output = {"message": "Analyst notification queued"}
        elif action == PlaybookAction.NOTIFY_COMMANDER:
            queue = context.setdefault("commander_alerts", [])
            queue.append(
                {
                    "case_id": case.case_id,
                    "priority": "critical",
                    "classification": case.classification,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            output = {"message": "Commander alert queued"}
        elif action == PlaybookAction.ESCALATE_CASE:
            case.status = CaseStatus.ESCALATED
            case.add_timeline_entry("case_escalated", "soar_engine", "Escalated by playbook step")
            output = {"message": "Case escalated"}
        elif action == PlaybookAction.ENRICH_OBSERVABLE:
            enrichments = self.ir_bridge.enrich_observables_from_dicts(case.observables)
            case.enrichments.extend([item.to_dict() for item in enrichments])
            if enrichments:
                context["enrichment_verdict"] = enrichments[-1].verdict
            output = {"enrichments": [item.to_dict() for item in enrichments]}
        elif action == PlaybookAction.QUERY_LLM:
            # Tactical note: local simulated Grok response keeps operation air-gapped.
            case.llm_analysis = (
                "Grok tactical analysis: Incident likely coordinated cyber activity. "
                "Prioritize containment, preserve forensic artifacts, and monitor lateral movement."
            )
            output = {"analysis": case.llm_analysis}
        elif action == PlaybookAction.GENERATE_REPORT:
            report = (
                f"S3M IR Report\nCase: {case.case_id}\nSeverity: {case.severity.value}\n"
                f"Status: {case.status.value}\nObservables: {len(case.observables)}\n"
                "Recommended next shift action: Continue containment and analyst validation."
            )
            context["generated_report"] = report
            output = {"report": report}
        else:
            output = {"message": "Custom action logged", "parameters": dict(step.parameters)}
        return output

    def execute_step(
        self,
        step: PlaybookStep,
        case: IncidentCase,
        context: dict,
        *,
        mission_envelope: Optional[MissionEnvelope] = None,
        approvals: Optional[Approvals] = None,
        manual_execution: bool = False,
    ) -> dict:
        started = time.perf_counter()
        output: Dict[str, Any] = {}
        status = "success"

        if is_forbidden_action(step.action):
            step.status = PlaybookStatus.ABORTED
            output = {
                "error": "forbidden_action",
                "forbidden": sorted(forbidden_playbook_actions()),
            }
            duration_ms = (time.perf_counter() - started) * 1000.0
            case.add_timeline_entry(
                "step_blocked",
                "soar_executor",
                f"Forbidden action blocked: {step.action.value}",
            )
            return {
                "step_id": step.step_id,
                "action": step.action.value,
                "status": "blocked",
                "output": output,
                "duration_ms": round(duration_ms, 3),
            }

        step_kind = self._step_kind(step)
        tool_name = resolve_tool_name(step.action, step.parameters)

        if step_kind == PlaybookStepKind.MUTATE:
            tool_call = ToolCall(
                tool_name=tool_name,
                case_id=case.case_id,
                step_id=step.step_id,
                step_kind=step_kind.value,
                parameters=dict(step.parameters),
            )
            decision = evaluate_soar_tool_call(
                tool_call,
                mission_envelope,
                approvals,
                auto_execute=self.auto_execute,
                manual_execution=manual_execution,
            )
            decision_dict = decision.to_dict()
            self._record_policy_decision(case, step, decision_dict)

            mutation_key = (case.case_id, step.step_id, tool_name)
            if mutation_key in self._executed_mutations:
                duration_ms = (time.perf_counter() - started) * 1000.0
                step.status = PlaybookStatus.COMPLETED
                return {
                    "step_id": step.step_id,
                    "action": step.action.value,
                    "status": "skipped",
                    "output": {"reason": "mutate_already_executed"},
                    "duration_ms": round(duration_ms, 3),
                }

            if not decision.allowed:
                return self._queue_mutate_step(step, case, decision_dict, started)

            self._executed_mutations.add(mutation_key)

        try:
            step.status = PlaybookStatus.RUNNING
            output = self._run_step_body(step, case, context)
            step.status = PlaybookStatus.COMPLETED
            step.result = dict(output)
        except Exception as exc:
            status = "failed"
            step.status = PlaybookStatus.FAILED
            step.result = {"error": str(exc)}
            output = {"error": str(exc)}
        duration_ms = (time.perf_counter() - started) * 1000.0
        return {
            "step_id": step.step_id,
            "action": step.action.value,
            "status": status,
            "output": output,
            "duration_ms": round(duration_ms, 3),
        }

    def execute(
        self,
        playbook: Playbook,
        case: IncidentCase,
        *,
        mission_envelope: Optional[MissionEnvelope] = None,
        approvals: Optional[Approvals] = None,
        manual_execution: bool = False,
    ) -> dict:
        started = time.perf_counter()
        context: Dict[str, Any] = {"case_id": case.case_id}
        results: List[dict] = []
        succeeded = failed = skipped = queued = 0
        for step in playbook.steps:
            if step.condition and not self._evaluate_condition(step.condition, case, context):
                skipped += 1
                step.status = PlaybookStatus.ABORTED
                results.append(
                    {
                        "step_id": step.step_id,
                        "action": step.action.value,
                        "status": "skipped",
                        "output": {"reason": "condition_not_met"},
                        "duration_ms": 0.0,
                    }
                )
                continue
            result = self.execute_step(
                step,
                case,
                context,
                mission_envelope=mission_envelope,
                approvals=approvals,
                manual_execution=manual_execution,
            )
            results.append(result)
            if result["status"] == "success":
                succeeded += 1
            elif result["status"] == "awaiting_approval":
                queued += 1
            elif result["status"] == "skipped":
                skipped += 1
            else:
                failed += 1
                if step.on_failure == "abort":
                    break
                if step.on_failure in {"continue", "skip"}:
                    continue
        duration_ms = (time.perf_counter() - started) * 1000.0
        summary = {
            "playbook_id": playbook.playbook_id,
            "case_id": case.case_id,
            "steps_executed": len(results),
            "steps_succeeded": succeeded,
            "steps_failed": failed,
            "steps_skipped": skipped,
            "steps_queued": queued,
            "auto_execute": self.auto_execute,
            "results": results,
            "duration_ms": round(duration_ms, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        case.playbook_results.extend(results)
        case.playbook_id = playbook.playbook_id
        case.add_timeline_entry("playbook_executed", "soar_executor", playbook.playbook_id)
        self._history.append(summary)
        if len(self._history) > 1000:
            del self._history[:-1000]
        return summary

    def get_approval_queue(self) -> List[dict]:
        return list(self._approval_queue)

    def get_execution_history(self, limit: int = 50) -> List[dict]:
        safe_limit = max(1, min(int(limit), 500))
        return list(reversed(self._history))[:safe_limit]
