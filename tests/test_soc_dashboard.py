"""Tests for SOC dashboard provider outputs."""

from __future__ import annotations

from services.cyber.models import CaseSeverity
from services.cyber.soc_manager import SOCManager
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


def _event(title: str = "SOC dashboard event") -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.MEDIUM,
        category=ThreatCategory.CYBER,
        title=title,
        description="SSH brute force from 198.51.100.5",
        raw_data={"src_ip": "198.51.100.5"},
        confidence=0.8,
    )


def test_get_soc_overview_returns_expected_keys():
    soc = SOCManager()
    soc.process_event(_event())
    overview = soc.soc_dashboard.get_soc_overview()
    for key in [
        "open_cases",
        "cases_by_severity",
        "cases_by_status",
        "mean_resolution_hours",
        "alerts_last_hour",
        "playbooks_executed_today",
        "platforms_online",
        "mitre_heatmap",
        "top_observables",
        "analyst_workload",
    ]:
        assert key in overview


def test_get_mitre_heatmap_returns_rows():
    soc = SOCManager()
    soc.process_event(_event())
    rows = soc.soc_dashboard.get_mitre_heatmap()
    assert isinstance(rows, list)
    if rows:
        assert "tactic_id" in rows[0]
        assert "technique_id" in rows[0]
        assert "count" in rows[0]


def test_get_alert_queue_returns_triaged_alerts():
    soc = SOCManager()
    triage = soc.alert_triage
    triage.auto_case_threshold = CaseSeverity.CRITICAL
    triage.triage(_event("Queue only"))
    queue = soc.soc_dashboard.get_alert_queue(limit=10)
    assert isinstance(queue, list)
    assert len(queue) >= 1


def test_get_ioc_feed_returns_recent_observables():
    soc = SOCManager()
    soc.process_event(_event())
    feed = soc.soc_dashboard.get_ioc_feed(limit=100)
    assert isinstance(feed, list)
    assert any(item.get("value") == "198.51.100.5" for item in feed)
