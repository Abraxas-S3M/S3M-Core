"""Build human-readable device payloads via the offline interpreter engine."""

from __future__ import annotations

from typing import Any, Dict, List

from services.comms.nlp import ArabicNLPEngine


class ChangePayloadBuilder:
    """Machine-generated EN/AR summaries plus exact tactical change metadata."""

    def __init__(self) -> None:
        # Tactical context: keyword backend keeps summaries offline on Jetson.
        self._engine = ArabicNLPEngine(model_backend="keyword")

    def build(
        self,
        *,
        change_id: str,
        envelope_id: str,
        diff: str,
        interpreter_context: str,
        risk_before: Dict[str, Any],
        risk_after: Dict[str, Any],
        blast_radius: Dict[str, Any],
        rollback_steps: List[str],
    ) -> Dict[str, Any]:
        source = interpreter_context.strip() or diff.strip() or f"change {change_id}"
        compact = self._engine.summarize(
            text=source,
            language="en",
            message_id=change_id,
            priority="high",
        )
        summary_en = (compact.summary_en or source)[:2000]
        summary_ar = (compact.summary_ar or summary_en)[:2000]
        return {
            "change_id": change_id,
            "envelope_id": envelope_id,
            "summary_en": summary_en,
            "summary_ar": summary_ar,
            "summaries_machine_generated": True,
            "diff": diff,
            "risk_before": risk_before,
            "risk_after": risk_after,
            "blast_radius": blast_radius,
            "rollback_steps": rollback_steps,
        }
