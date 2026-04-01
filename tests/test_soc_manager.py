"""Tests for SOCManager end-to-end orchestration."""

from __future__ import annotations

from services.cyber.models import CaseVerdict
from services.cyber.soc_manager import SOCManager
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


def _event(title: str, level: ThreatLevel = ThreatLevel.HIGH) -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=level,
        category=ThreatCategory.CYBER,
        title=title,
        description=f"{title} with SSH brute force and source 198.51.100.42",
        raw_data={"src_ip": "198.51.100.42", "url": "http://mal.example.com"},
        confidence=0.9,
        classification="UNCLASSIFIED - FOUO",
    )


def test_process_event_pipeline():
    manager = SOCManager()
    result = manager.process_event(_event("Pipeline event"))
    assert "triage" in result
    assert "logs" in result
    assert result["triage"]["auto_create_case"] is True
    assert result["case_id"] is not None


def test_process_batch_multiple():
    manager = SOCManager()
    result = manager.process_batch([_event("E1"), _event("E2", level=ThreatLevel.MEDIUM)])
    assert result["processed"] == 2
    assert "results" in result


def test_generate_soc_report_non_empty():
    manager = SOCManager()
    manager.process_event(_event("Report seed"))
    report = manager.generate_soc_report()
    assert isinstance(report, str)
    assert report.strip()


def test_get_soc_status_shape():
    manager = SOCManager()
    status = manager.get_soc_status()
    for key in ["triage", "cases", "platforms", "soar", "logs", "dashboard", "training"]:
        assert key in status


def test_resolve_case_through_manager():
    manager = SOCManager()
    result = manager.process_event(_event("Resolve case"))
    case_id = result["case_id"]
    assert case_id
    case = manager.resolve_case(case_id, CaseVerdict.TRUE_POSITIVE.value, "Confirmed compromise")
    assert case.verdict == CaseVerdict.TRUE_POSITIVE
