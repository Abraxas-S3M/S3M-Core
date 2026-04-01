"""Tests for SOC case manager lifecycle and stats behaviors."""

from __future__ import annotations

from services.cyber.models import CaseSeverity, CaseStatus, CaseVerdict, Observable, ObservableType
from services.cyber.triage.case_manager import CaseManager
from services.cyber.triage.alert_triage import AlertTriage
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


def _event(title: str = "SSH brute force") -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.HIGH,
        category=ThreatCategory.CYBER,
        title=title,
        description="SSH brute force from 198.51.100.10",
        raw_data={"src_ip": "198.51.100.10"},
        confidence=0.9,
    )


def test_create_case_and_retrieve():
    manager = CaseManager()
    case = manager.create_case(
        title="Test case",
        description="desc",
        severity=CaseSeverity.MEDIUM,
        source_events=["e1"],
    )
    fetched = manager.get_case(case.case_id)
    assert fetched is not None
    assert fetched.case_id == case.case_id


def test_create_from_triage_auto_populates_fields():
    triage = AlertTriage()
    event = _event()
    triage_result = triage.triage(event)
    manager = CaseManager()
    case = manager.create_from_triage(triage_result, event)
    assert case.source_events == [event.event_id]
    assert len(case.observables) >= 1


def test_assign_analyst_adds_timeline_entry():
    manager = CaseManager()
    case = manager.create_case("c1", "d1", CaseSeverity.HIGH, ["e1"])
    before = len(case.timeline)
    manager.assign_analyst(case.case_id, "analyst-1")
    updated = manager.get_case(case.case_id)
    assert updated is not None
    assert updated.assigned_analyst == "analyst-1"
    assert len(updated.timeline) > before


def test_escalate_changes_status_to_escalated():
    manager = CaseManager()
    case = manager.create_case("c1", "d1", CaseSeverity.HIGH, ["e1"])
    manager.escalate(case.case_id, "critical impact")
    updated = manager.get_case(case.case_id)
    assert updated is not None
    assert updated.status == CaseStatus.ESCALATED


def test_resolve_sets_verdict_and_resolved_at():
    manager = CaseManager()
    case = manager.create_case("c1", "d1", CaseSeverity.HIGH, ["e1"])
    manager.resolve(case.case_id, CaseVerdict.TRUE_POSITIVE, "confirmed")
    updated = manager.get_case(case.case_id)
    assert updated is not None
    assert updated.verdict == CaseVerdict.TRUE_POSITIVE
    assert updated.resolved_at is not None


def test_get_cases_filters_by_status_and_severity():
    manager = CaseManager()
    c1 = manager.create_case("c1", "d1", CaseSeverity.LOW, ["e1"])
    c2 = manager.create_case("c2", "d2", CaseSeverity.HIGH, ["e2"])
    manager.assign_analyst(c2.case_id, "ana")
    manager.resolve(c1.case_id, CaseVerdict.BENIGN, "done")
    resolved = manager.get_cases(status="RESOLVED")
    high = manager.get_cases(severity="HIGH")
    assert all(case.status == CaseStatus.RESOLVED for case in resolved)
    assert all(case.severity == CaseSeverity.HIGH for case in high)


def test_get_stats_returns_correct_counts():
    manager = CaseManager()
    c1 = manager.create_case("c1", "d1", CaseSeverity.LOW, ["e1"])
    manager.resolve(c1.case_id, CaseVerdict.BENIGN, "done")
    stats = manager.get_stats()
    assert stats["total"] == 1
    assert stats["by_status"]["RESOLVED"] == 1
    assert stats["by_severity"]["LOW"] == 1


def test_max_cases_fifo_rotation():
    manager = CaseManager(max_cases=2)
    a = manager.create_case("a", "d", CaseSeverity.LOW, ["e1"])
    b = manager.create_case("b", "d", CaseSeverity.LOW, ["e2"])
    c = manager.create_case("c", "d", CaseSeverity.LOW, ["e3"])
    assert manager.get_case(a.case_id) is None
    assert manager.get_case(b.case_id) is not None
    assert manager.get_case(c.case_id) is not None
