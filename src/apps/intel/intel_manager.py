"""Central orchestration manager for Phase 19 intelligence center."""

from __future__ import annotations

from src.apps.intel.briefings import BriefingGenerator
from src.apps.intel.intel_dashboard import IntelDashboardProvider
from src.apps.intel.models import CrisisEvent, DailyBrief, IntelReport, OSINTItem, WarningIndicator, WeeklyEstimate
from src.apps.intel.runtime import get_shared_intel_state


class IntelManager:
    """Coordinate collection, monitoring, briefing, and dashboard workflows."""

    def __init__(self):
        self.state = get_shared_intel_state()
        self.collector = self.state["collector"]
        self.monitor = self.state["monitor"]
        self.briefing: BriefingGenerator = self.state["briefing"]
        self.dashboard = IntelDashboardProvider()

    def collect_and_analyze(self) -> dict:
        result = self.collector.collect()
        monitor = self.monitor.update(self.collector.get_items(limit=50000))
        return {"collection": result, "monitoring": monitor}

    def generate_daily_brief(self, date=None) -> DailyBrief:
        brief = self.briefing.daily.generate(date=date)
        self.state["brief_history"]["daily"].append(brief)
        return brief

    def generate_weekly_estimate(self, week=None) -> WeeklyEstimate:
        estimate = self.briefing.weekly.generate(week=week)
        self.state["brief_history"]["weekly"].append(estimate)
        return estimate

    def generate_sitrep(self, region) -> IntelReport:
        crises = self.monitor.crisis_tracker.get_active_crises(region=region)
        return self.briefing.product_factory.generate_sitrep(
            region=region,
            items=self.collector.get_items(region=region, limit=5000),
            crisis_events=crises,
        )

    def generate_intsum(self, period="24h") -> IntelReport:
        return self.briefing.product_factory.generate_intsum(
            items=self.collector.get_items(limit=10000),
            period=period,
        )

    def generate_threat_assessment(self, region, topic) -> IntelReport:
        return self.briefing.product_factory.generate_threat_assessment(
            region=region,
            topic=topic,
            items=self.collector.get_items(region=region, topic=topic, limit=10000),
        )

    def search_intel(self, query) -> list[OSINTItem]:
        return self.collector.search(query)

    def get_crises(self) -> list[CrisisEvent]:
        return self.monitor.crisis_tracker.get_active_crises()

    def get_warnings(self) -> list[WarningIndicator]:
        return self.monitor.early_warning.get_active_warnings()

    def get_intel_overview(self) -> dict:
        return self.dashboard.get_intel_overview()

    def get_region_intel(self, region) -> dict:
        return self.dashboard.get_region_intel(region)

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "collector": self.collector.health_check(),
            "monitor": self.monitor.health_check(),
            "briefings": {
                "reports_generated": len(self.briefing.product_factory.list_reports()),
                "daily_history": len(self.state["brief_history"]["daily"]),
                "weekly_history": len(self.state["brief_history"]["weekly"]),
            },
            "dashboard": {
                "region_views_available": len(self.monitor.risk_scorer.get_all_scores()),
            },
        }
