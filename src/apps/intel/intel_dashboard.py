"""Dashboard data provider for Phase 19 Intelligence Center."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.apps.intel.runtime import get_shared_intel_state


class IntelDashboardProvider:
    """Provide intelligence center dashboard payloads for Layer 06 integration."""

    def __init__(self):
        self.state = get_shared_intel_state()

    def get_intel_overview(self) -> dict:
        now = datetime.now(timezone.utc)
        items_24h = [
            item
            for item in self.state["collector"].get_items(limit=50000)
            if item.timestamp.astimezone(timezone.utc) >= now - timedelta(hours=24)
        ]
        items_7d = [
            item
            for item in self.state["collector"].get_items(limit=50000)
            if item.timestamp.astimezone(timezone.utc) >= now - timedelta(days=7)
        ]
        sources = self.state["collector"].source_manager.get_sources(active_only=False)
        crises = self.state["monitor"].crisis_tracker.get_active_crises()
        warnings = [row["indicator"] for row in self.state["monitor"].early_warning.check_all() if row["triggered"]]
        risk_by_region = {
            region: row["score"]
            for region, row in self.state["monitor"].risk_scorer.get_all_scores().items()
        }
        crises_by_region: dict[str, int] = {}
        for crisis in crises:
            crises_by_region[crisis.region] = crises_by_region.get(crisis.region, 0) + 1
        top_events = [
            {
                "item_id": item.item_id,
                "title": item.title,
                "region": item.regions[0] if item.regions else "Global",
                "relevance_score": item.relevance_score,
                "sentiment": item.sentiment,
            }
            for item in sorted(
                self.state["collector"].get_items(limit=500),
                key=lambda row: row.relevance_score,
                reverse=True,
            )[:10]
        ]
        latest_brief = None
        if self.state["brief_history"]["daily"]:
            latest_brief = self.state["brief_history"]["daily"][-1].to_dict()
        return {
            "items_last_24h": len(items_24h),
            "items_last_7d": len(items_7d),
            "sources_active": len([source for source in sources if source.active]),
            "sources_by_type": self.state["collector"].source_manager.get_source_stats()["by_type"],
            "crises_active": len(crises),
            "crises_by_region": crises_by_region,
            "warnings_triggered": warnings,
            "risk_by_region": risk_by_region,
            "top_events": top_events,
            "latest_brief": latest_brief,
            "collection_health": self.state["collector"].health_check(),
        }

    def get_region_intel(self, region: str) -> dict:
        items = self.state["collector"].get_items(region=region, limit=200)
        crises = [row.to_dict() for row in self.state["monitor"].crisis_tracker.get_active_crises(region=region)]
        warnings = [
            indicator.to_dict()
            for indicator in self.state["monitor"].early_warning.get_active_warnings()
            if region.lower() in indicator.region.lower() or indicator.region.lower() == "all regions"
        ]
        risk = self.state["monitor"].risk_scorer.get_score(region)
        reports = [
            report.to_dict()
            for report in self.state["briefing"].product_factory.list_reports()
            if region in report.regions
        ][:20]
        return {
            "region": region,
            "items": [item.to_dict() for item in items],
            "crises": crises,
            "risk": risk,
            "warnings": warnings,
            "recent_reports": reports,
        }

    def get_crisis_board(self) -> list[dict]:
        return [
            {
                "event_id": crisis.event_id,
                "name": crisis.name,
                "region": crisis.region,
                "severity": crisis.severity.value,
                "status": crisis.status,
                "last_update": crisis.last_updated.isoformat(),
                "timeline_length": len(crisis.timeline),
            }
            for crisis in self.state["monitor"].crisis_tracker.get_active_crises()
        ]

    def get_source_health(self) -> list[dict]:
        return [
            {
                "source_id": source.source_id,
                "name": source.name,
                "active": source.active,
                "last_ingestion": source.last_ingestion.isoformat() if source.last_ingestion else None,
                "items_count": source.items_ingested,
                "reliability": source.reliability.value,
                "type": source.source_type.value,
            }
            for source in self.state["collector"].source_manager.get_sources(active_only=False)
        ]
