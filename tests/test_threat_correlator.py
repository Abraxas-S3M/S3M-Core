"""Tests for Phase 11 threat hunting module components."""

from src.apps.threat_hunting.escalation_manager import EscalationManager
from src.apps.threat_hunting.threat_correlator import ThreatCorrelator


def _event(event_id: str, ts: str, category: str, level: str, source: str, pos=(0.0, 0.0, 0.0), actor=None):
    return {
        "event_id": event_id,
        "timestamp": ts,
        "category": category,
        "level": level,
        "source": source,
        "actor": actor or source,
        "position": pos,
    }


def test_correlate_groups_events_within_time_window():
    correlator = ThreatCorrelator(time_window_seconds=300, distance_threshold=500)
    events = [
        _event("e1", "2026-01-01T10:00:00+00:00", "CYBER", "LOW", "src-a"),
        _event("e2", "2026-01-01T10:01:00+00:00", "CYBER", "MEDIUM", "src-a"),
        _event("e3", "2026-01-01T10:02:00+00:00", "CYBER", "HIGH", "src-a"),
    ]
    correlations = correlator.correlate(events)
    assert len(correlations) >= 1


def test_coordinated_cyber_pattern():
    correlator = ThreatCorrelator()
    events = [
        _event("c1", "2026-01-01T10:00:00+00:00", "CYBER", "LOW", "same-source"),
        _event("c2", "2026-01-01T10:01:00+00:00", "CYBER", "MEDIUM", "same-source"),
        _event("c3", "2026-01-01T10:02:00+00:00", "CYBER", "HIGH", "same-source"),
    ]
    patterns = [item["pattern"] for item in correlator.correlate(events)]
    assert "coordinated_cyber" in patterns


def test_multi_domain_pattern():
    correlator = ThreatCorrelator()
    events = [
        _event("m1", "2026-01-01T10:00:00+00:00", "CYBER", "MEDIUM", "src-c", pos=(0, 0, 0)),
        _event("m2", "2026-01-01T10:01:00+00:00", "KINETIC", "HIGH", "src-k", pos=(10, 10, 0)),
    ]
    patterns = [item["pattern"] for item in correlator.correlate(events)]
    assert "multi_domain" in patterns


def test_no_correlation_for_widely_separated_events():
    correlator = ThreatCorrelator(time_window_seconds=60, distance_threshold=50)
    events = [
        _event("w1", "2026-01-01T10:00:00+00:00", "CYBER", "LOW", "s1", pos=(0, 0, 0)),
        _event("w2", "2026-01-01T11:30:00+00:00", "KINETIC", "HIGH", "s2", pos=(5000, 5000, 0)),
    ]
    correlations = correlator.correlate(events)
    assert correlations == []


def test_escalation_manager_evaluates_critical_threat():
    manager = EscalationManager()
    out = manager.evaluate({"event_id": "critical-1", "level": "CRITICAL", "category": "KINETIC", "confidence": 0.9})
    assert out is not None
    assert out["rule_name"] in {"critical_immediate", "weapons_system_threat"}


def test_escalation_rule_add_remove():
    manager = EscalationManager()
    manager.add_rule(
        name="test_rule",
        condition="category == CYBER and confidence > 0.1",
        action="notify_soc",
        auto_response=True,
        priority=2,
    )
    names = [rule["name"] for rule in manager.get_rules()]
    assert "test_rule" in names
    manager.remove_rule("test_rule")
    names = [rule["name"] for rule in manager.get_rules()]
    assert "test_rule" not in names
