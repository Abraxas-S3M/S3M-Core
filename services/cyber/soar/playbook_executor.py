"""Execution runtime for SOC SOAR playbooks."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from services.cyber.ir_platforms.ir_bridge import IRPlatformBridge
from services.cyber.models import (
    CaseStatus,
    IncidentCase,
    Playbook,
    PlaybookAction,
    PlaybookStatus,
    PlaybookStep,
)


class PlaybookExecutor:
    """Executes tactical SOC playbook steps with defensive failure handling."""

    def __init__(self, ir_bridge: object = None) -> None:
        self.ir_bridge = ir_bridge if ir_bridge is not None else IRPlatformBridge()
        self._history: List[dict] = []

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

    def execute_step(self, step: PlaybookStep, case: IncidentCase, context: dict) -> dict:
        started = time.perf_counter()
        output: Dict[str, Any] = {}
        status = "success"
        try:
            step.status = PlaybookStatus.RUNNING
            action = step.action
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

    def execute(self, playbook: Playbook, case: IncidentCase) -> dict:
        started = time.perf_counter()
        context: Dict[str, Any] = {"case_id": case.case_id}
        results: List[dict] = []
        succeeded = failed = skipped = 0
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
            result = self.execute_step(step, case, context)
            results.append(result)
            if result["status"] == "success":
                succeeded += 1
            else:
                failed += 1
                if step.on_failure == "abort":
                    break
                if step.on_failure == "skip":
                    continue
        duration_ms = (time.perf_counter() - started) * 1000.0
        summary = {
            "playbook_id": playbook.playbook_id,
            "case_id": case.case_id,
            "steps_executed": len(results),
            "steps_succeeded": succeeded,
            "steps_failed": failed,
            "steps_skipped": skipped,
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

    def get_execution_history(self, limit: int = 50) -> List[dict]:
        safe_limit = max(1, min(int(limit), 500))
        return list(reversed(self._history))[:safe_limit]
