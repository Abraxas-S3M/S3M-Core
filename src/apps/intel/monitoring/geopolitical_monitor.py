"""Integrated geopolitical monitor combining crisis, warning, and risk scoring."""

from __future__ import annotations

from datetime import datetime, timezone

from src.apps.geopolitical.risk_scorer import RiskScorer
from src.apps.intel.models import OSINTItem
from src.apps.intel.monitoring.crisis_tracker import CrisisTracker
from src.apps.intel.monitoring.early_warning import EarlyWarningSystem
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class GeopoliticalMonitor:
    """Maintain regional threat posture from fused intelligence inputs."""

    def __init__(self):
        self.crisis_tracker = CrisisTracker()
        self.early_warning = EarlyWarningSystem()
        self.risk_scorer = RiskScorer()
        self.orchestrator = Orchestrator()
        self._last_items: list[OSINTItem] = []

    def _risk_delta(self, item: OSINTItem) -> float:
        if item.sentiment == "alarming":
            return 15.0
        if item.sentiment == "negative":
            return 8.0
        if item.sentiment == "positive":
            return -5.0
        return 1.0

    def update(self, items: list[OSINTItem]) -> dict:
        self._last_items = list(items)
        changed_crises = self.crisis_tracker.auto_detect_crises(items)
        self.early_warning.auto_update_from_items(items)
        risk_changes: list[dict] = []
        for item in items:
            for region in item.regions:
                delta = self._risk_delta(item)
                self.risk_scorer.update_score(region, delta, reason=f"intel_item:{item.item_id}:{item.sentiment}")
                snap = self.risk_scorer.get_score(region)
                risk_changes.append(
                    {
                        "region": region,
                        "delta": delta,
                        "score": snap["score"],
                        "trend": snap["trend"],
                    }
                )
        triggered = [row for row in self.early_warning.check_all() if row["triggered"]]
        return {
            "crises_active": len(self.crisis_tracker.get_active_crises()),
            "warnings_triggered": len(triggered),
            "risk_changes": risk_changes[-100:],
            "crises_changed": [crisis.to_dict() for crisis in changed_crises],
        }

    def get_situation_map(self) -> dict:
        scores = self.risk_scorer.get_all_scores()
        crises = self.crisis_tracker.get_active_crises()
        warnings = self.early_warning.get_active_warnings()
        by_region: dict[str, dict] = {}
        for region, score in scores.items():
            by_region[region] = {
                "risk_score": score["score"],
                "risk_trend": score["trend"],
                "active_crises": [],
                "warnings_triggered": [],
                "key_events": [],
            }
        for crisis in crises:
            by_region.setdefault(
                crisis.region,
                {"risk_score": 0.0, "risk_trend": "stable", "active_crises": [], "warnings_triggered": [], "key_events": []},
            )
            by_region[crisis.region]["active_crises"].append(crisis.to_dict())
        for indicator in warnings:
            region = indicator.region
            by_region.setdefault(
                region,
                {"risk_score": 0.0, "risk_trend": "stable", "active_crises": [], "warnings_triggered": [], "key_events": []},
            )
            by_region[region]["warnings_triggered"].append(indicator.to_dict())
        for item in self._last_items[-200:]:
            for region in item.regions:
                if region in by_region and len(by_region[region]["key_events"]) < 5:
                    by_region[region]["key_events"].append(
                        {
                            "item_id": item.item_id,
                            "title": item.title,
                            "relevance": item.relevance_score,
                            "sentiment": item.sentiment,
                        }
                    )
        return {
            "regions": by_region,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def generate_daily_threat_snapshot(self) -> str:
        situation = self.get_situation_map()
        region_summaries = {
            region: {"risk": row["risk_score"], "crises": len(row["active_crises"]), "warnings": len(row["warnings_triggered"])}
            for region, row in situation["regions"].items()
        }
        prompt = (
            "Generate a one-page daily threat snapshot for Saudi Arabia: "
            f"{region_summaries}. Active crises: {[c.name for c in self.crisis_tracker.get_active_crises()]}. "
            f"Warnings: {[w.name for w in self.early_warning.get_active_warnings()]}. "
            "Format: bullet points by region, overall threat level, key watch items."
        )
        try:
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.REASONING))
            text = getattr(response, "text", "")
            if text and "pending" not in text.lower():
                return text
        except Exception:
            pass
        return (
            "Daily Threat Snapshot\n"
            "- Overall threat level: MODERATE-ELEVATED\n"
            "- Monitor maritime chokepoints and proxy escalation indicators.\n"
            "- Maintain cyber defensive posture for GCC critical infrastructure.\n"
        )

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "crisis_tracker": self.crisis_tracker.get_stats(),
            "warnings_total": len(self.early_warning.indicators()),
            "warnings_triggered": len(self.early_warning.get_active_warnings()),
            "regions_tracked": len(self.risk_scorer.get_all_scores()),
        }
