"""Decision workspace adapter.

Wraps AutonomyDashProvider to provide decision queue CRUD with the
GUI's expected response shapes, including queueCounts.

Internal dependencies:
- src.dashboard.providers.autonomy_dash_provider.AutonomyDashProvider
- src.api.gui_bridge.ws_bridge.emit_to_gui (for real-time updates)
- src.api.gui_bridge.timeline_service.timeline_service (for event logging)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.api.gui_bridge.models.gui_schemas import (
    GUIDecision,
    GUIDecisionExplanation,
    GUIDissentingView,
    GUIDoctrineCheck,
    GUIEvidenceItem,
    DecisionStatus,
    SeverityLevel,
)
from src.api.gui_bridge.training_emitter import emit_training_record

DECISION_EXPLANATION_LOG_PATH = Path("data/training/decision_explanations.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_percent(score: Any) -> int:
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 1.0:
        value *= 100.0
    return int(min(100.0, max(0.0, value)))


def _score_to_severity(score: float) -> SeverityLevel:
    s = float(score) if score else 0.0
    if s <= 1.0:
        s = s * 100.0
    if s >= 80:
        return SeverityLevel.CRITICAL
    if s >= 60:
        return SeverityLevel.HIGH
    if s >= 40:
        return SeverityLevel.MEDIUM
    return SeverityLevel.LOW


def _append_explanation_training_record(decision_id: str, response: Dict[str, Any]) -> None:
    record = {
        "requestedAt": _now_iso(),
        "decisionId": decision_id,
        "response": response,
    }
    try:
        DECISION_EXPLANATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DECISION_EXPLANATION_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        pass


class DecisionAdapter:
    def __init__(self) -> None:
        from src.dashboard.providers.autonomy_dash_provider import AutonomyDashProvider

        self._autonomy = AutonomyDashProvider()
        self._store = None
        self._use_store_decisions = False
        try:
            from src.persistence.store_seeder import seed_store_if_empty

            self._store = seed_store_if_empty()
            self._use_store_decisions = self._store.has_data("decisions")
        except Exception:
            pass

    def _build_decision_context(self, decision_id: str) -> Dict[str, Any]:
        """Build doctrine context for tactical ROE compliance checks."""
        context: Dict[str, Any] = {
            "decision_id": decision_id,
            "target_type": "unknown",
            "positive_id": False,
            "near_civilian_zone": False,
        }
        try:
            all_decisions = self._autonomy.get_decision_feed(limit=500)
            match = next(
                (item for item in all_decisions if str(item.get("id", "")).strip() == decision_id),
                None,
            )
            if not match:
                return context
            context["target_type"] = str(match.get("target_type", match.get("type", "unknown")))
            context["positive_id"] = bool(
                match.get("positive_id", match.get("is_positive_id", False))
            )
            context["near_civilian_zone"] = bool(
                match.get(
                    "near_civilian_zone",
                    match.get("civilian_zone_proximity", False),
                )
            )
        except Exception:
            pass
        return context

    def get_queue(self) -> Dict[str, Any]:
        """Return full decision queue with counts for the GUI."""
        all_decisions = self._autonomy.get_decision_feed(limit=500)
        if self._store is not None and isinstance(all_decisions, list) and all_decisions:
            for row in all_decisions:
                if isinstance(row, dict):
                    self._store.upsert("decisions", row)
            self._use_store_decisions = True
        elif self._store is not None and self._use_store_decisions:
            all_decisions = self._store.get_all("decisions")
        gui_decisions = []
        counts = {"pending": 0, "autoApproved": 0, "humanApproved": 0, "vetoed": 0, "stale": 0}

        for d in all_decisions:
            status_raw = str(d.get("status", "pending")).lower()
            risk_raw = d.get("risk_score", 0.5)
            risk_int = _to_percent(risk_raw)
            conf_raw = d.get("confidence", 0.5)
            conf_int = _to_percent(conf_raw)

            if status_raw == "pending":
                counts["pending"] += 1
                ds = DecisionStatus.PENDING
            elif status_raw == "approved":
                if bool(d.get("requires_review", False)):
                    counts["humanApproved"] += 1
                else:
                    counts["autoApproved"] += 1
                ds = DecisionStatus.APPROVED
            elif status_raw == "rejected":
                counts["vetoed"] += 1
                ds = DecisionStatus.REJECTED
            else:
                counts["stale"] += 1
                ds = DecisionStatus.PENDING

            gui_decisions.append(
                GUIDecision(
                    id=str(d.get("id", "")),
                    title=str(d.get("type", "UNKNOWN")).upper(),
                    risk=risk_int,
                    confidence=conf_int,
                    description=str(d.get("reasoning_snippet", d.get("context", ""))),
                    status=ds,
                    severity=_score_to_severity(risk_int),
                    updatedAt=str(d.get("timestamp", _now_iso())),
                ).model_dump()
            )

        result = {
            "decisions": gui_decisions,
            "queueCounts": counts,
            "updatedAt": _now_iso(),
        }
        emit_training_record("decision", {"query": "queue"}, result)
        return result

    def get_explanation(self, decision_id: str) -> Dict[str, Any]:
        safe_decision_id = str(decision_id).strip() or "unknown"
        explanation = {
            "decisionId": safe_decision_id,
            "evidence": [],
            "confidenceBreakdown": {},
            "dissentingViews": [],
            "doctrineChecks": [],
            "expectedUpside": [],
            "expectedDownside": [],
            "updatedAt": _now_iso(),
        }

        try:
            from src.autonomy.xai import get_explanation_for_decision

            xai_result = get_explanation_for_decision(safe_decision_id)
            explanation["evidence"] = [
                GUIEvidenceItem(**item).model_dump() for item in xai_result.get("evidence", [])
            ]
            explanation["confidenceBreakdown"] = {
                str(k): float(v) for k, v in xai_result.get("confidenceBreakdown", {}).items()
            }
            explanation["expectedUpside"] = [
                str(item) for item in xai_result.get("expectedUpside", [])
            ]
            explanation["expectedDownside"] = [
                str(item) for item in xai_result.get("expectedDownside", [])
            ]
        except Exception:
            pass

        try:
            from src.cognitive.multi_objective_resolver import MultiObjectiveResolver

            resolver = MultiObjectiveResolver()
            alternatives = (
                resolver.get_pareto_alternatives(safe_decision_id)
                if hasattr(resolver, "get_pareto_alternatives")
                else []
            )
            explanation["dissentingViews"] = [
                GUIDissentingView(**item).model_dump() for item in alternatives
            ]
        except Exception:
            pass

        try:
            from src.doctrine.opa_evaluator import OPAEvaluator

            doctrine_context = self._build_decision_context(safe_decision_id)
            doctrine_result = OPAEvaluator().evaluate_decision(doctrine_context)
            violations = [str(item) for item in doctrine_result.get("violations", []) if str(item).strip()]
            details = (
                "; ".join(violations)
                if violations
                else "Rules of engagement check passed for current tactical context."
            )
            explanation["doctrineChecks"] = [
                GUIDoctrineCheck(
                    policyName=str(doctrine_result.get("policy", "s3m.roe")),
                    compliant=bool(doctrine_result.get("compliant", False)),
                    details=details,
                ).model_dump()
            ]
        except Exception:
            pass

        response = GUIDecisionExplanation(**explanation).model_dump()
        _append_explanation_training_record(safe_decision_id, response)
        return response

    async def approve(self, decision_id: str, comment: str = "") -> Dict[str, Any]:
        result = self._autonomy.apply_review_decision(decision_id, approved=True, reason=comment)
        if result.get("status") == "error":
            return {"error": result.get("detail", "Approval failed"), "statusCode": 404}

        try:
            from src.api.gui_bridge.timeline_service import timeline_service
            from src.api.gui_bridge.ws_bridge import emit_to_gui

            await emit_to_gui("decision.updated", {"id": decision_id, "status": "approved"})
            timeline_service.emit(
                title=f"Decision {decision_id} approved",
                category="decision",
                severity="MEDIUM",
                details=comment or "Commander approved via GUI",
            )
        except Exception:
            pass

        return {"status": "approved", "decisionId": decision_id, "updatedAt": _now_iso()}

    async def reject(self, decision_id: str, comment: str = "") -> Dict[str, Any]:
        result = self._autonomy.apply_review_decision(decision_id, approved=False, reason=comment)
        if result.get("status") == "error":
            return {"error": result.get("detail", "Rejection failed"), "statusCode": 404}

        try:
            from src.api.gui_bridge.timeline_service import timeline_service
            from src.api.gui_bridge.ws_bridge import emit_to_gui

            await emit_to_gui("decision.updated", {"id": decision_id, "status": "rejected"})
            timeline_service.emit(
                title=f"Decision {decision_id} rejected",
                category="decision",
                severity="HIGH",
                details=comment or "Commander rejected via GUI",
            )
        except Exception:
            pass

        return {"status": "rejected", "decisionId": decision_id, "updatedAt": _now_iso()}
