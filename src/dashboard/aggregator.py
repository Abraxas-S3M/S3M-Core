"""Layer 06 dashboard aggregator coordinating all tactical providers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.dashboard.providers.alert_manager import AlertManager
from src.dashboard.providers.autonomy_dash_provider import AutonomyDashProvider
from src.dashboard.providers.cop_provider import COPDataProvider
from src.dashboard.providers.llm_monitor_provider import LLMMonitorProvider
from src.dashboard.providers.system_health_provider import SystemHealthProvider
from src.dashboard.providers.threat_dash_provider import ThreatDashProvider


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DashboardAggregator:
    """Central coordinator for Layer 06 dashboard data access."""

    def __init__(self) -> None:
        self.cop_provider = COPDataProvider()
        self.llm_provider = LLMMonitorProvider()
        self.threat_provider = ThreatDashProvider()
        self.autonomy_provider = AutonomyDashProvider()
        self.system_provider = SystemHealthProvider()
        self.alert_manager = AlertManager(
            threat_provider=self.threat_provider,
            autonomy_provider=self.autonomy_provider,
            system_provider=self.system_provider,
        )

    def get_overview(self) -> Dict[str, Any]:
        """Return single-call overview for all S3M dashboard tiles."""
        llm_metrics = self.llm_provider.get_metrics()
        threat_stats = self.threat_provider.get_threat_stats()
        missions = self.autonomy_provider.get_missions()
        review_queue = self.autonomy_provider.get_review_queue()
        roster = self.autonomy_provider.get_agent_roster()
        sim = self.system_provider.get_simulation_status()
        gps = self.system_provider.get_gps_status()
        jetson = self.system_provider.get_jetson_stats()
        paths = self.cop_provider.get_paths()

        return {
            "timestamp": _now_iso(),
            "llm": {
                "engines_loaded": int(llm_metrics.get("engines_loaded", 0)),
                "total_requests": int(llm_metrics.get("total_requests", 0)),
                "status": "operational",
            },
            "threats": {
                "total_events": int(threat_stats.get("total_events", 0)),
                "critical": int(threat_stats.get("by_level", {}).get("CRITICAL", 0)),
                "high": int(threat_stats.get("by_level", {}).get("HIGH", 0)),
                "active_sensors": int(threat_stats.get("active_sensors", 0)),
            },
            "autonomy": {
                "total_agents": len(roster),
                "active_missions": sum(
                    1 for mission in missions if str(mission.get("status", "")).lower() == "active"
                ),
                "decisions_pending_review": len(review_queue),
            },
            "simulation": {
                "running_scenarios": int(sim.get("running_scenarios", 0)),
                "datasets_generated": int(sim.get("datasets_generated", 0)),
            },
            "navigation": {
                "localization_mode": str(gps.get("mode", "unknown")),
                "gps_quality": str(gps.get("quality", "unknown")),
                "active_plans": len(paths),
            },
            "system": {
                "gpu_util_pct": float(jetson.get("gpu_util_pct", 0)),
                "memory_pct": float(jetson.get("memory_pct", 0)),
                "temperature_c": float(jetson.get("temperature_c", 0)),
                "uptime_seconds": float(llm_metrics.get("uptime_seconds", 0)),
            },
        }

    def get_alerts(self, level: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get dashboard alerts with optional severity filtering."""
        return self.alert_manager.collect(level=level, limit=limit)

    def health_check(self) -> Dict[str, Any]:
        """Report provider availability and layer reachability."""
        providers = {
            "cop": self.cop_provider.health_check(),
            "llm": self.llm_provider.health_check(),
            "threats": self.threat_provider.health_check(),
            "autonomy": self.autonomy_provider.health_check(),
            "system": self.system_provider.health_check(),
            "alerts": self.alert_manager.health_check(),
        }
        active = sum(1 for status in providers.values() if status.get("status") == "operational")
        total = len(providers)
        return {
            "timestamp": _now_iso(),
            "status": "operational" if active >= max(3, total // 2) else "degraded",
            "active_providers": active,
            "total_providers": total,
            "providers": providers,
        }
