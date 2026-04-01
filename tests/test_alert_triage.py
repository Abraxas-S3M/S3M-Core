"""Tests for SOC alert triage pipeline."""

from __future__ import annotations

from services.cyber.models import CaseSeverity
from services.cyber.triage import AlertTriage
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


def _event(level: ThreatLevel, description: str, raw_data: dict) -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=level,
        category=ThreatCategory.CYBER,
        title="SOC triage input",
        description=description,
        raw_data=raw_data,
        confidence=0.8,
    )


def test_triage_extracts_ip_observables():
    triage = AlertTriage()
    event = _event(
        ThreatLevel.MEDIUM,
        "Suspicious network activity",
        {"src_ip": "10.1.2.3", "dest_ip": "192.168.0.1"},
    )
    result = triage.triage(event)
    values = [obs.value for obs in result["observables"]]
    assert "10.1.2.3" in values
    assert "192.168.0.1" in values


def test_triage_extracts_sha256_hash():
    triage = AlertTriage()
    sha = "a" * 64
    event = _event(ThreatLevel.HIGH, "Malware hash seen", {"sha256": sha})
    result = triage.triage(event)
    assert any(obs.value == sha for obs in result["observables"])


def test_triage_maps_critical_to_case_critical():
    triage = AlertTriage()
    event = _event(ThreatLevel.CRITICAL, "Critical event", {"value": "x"})
    result = triage.triage(event)
    assert result["severity"] == CaseSeverity.CRITICAL


def test_triage_maps_mitre_for_ssh_brute_force():
    triage = AlertTriage()
    event = _event(ThreatLevel.HIGH, "SSH brute force from external IP", {"src_ip": "203.0.113.9"})
    result = triage.triage(event)
    assert result["mitre"] is not None
    assert result["mitre"].technique_id == "T1110"


def test_triage_score_calculation_in_range():
    triage = AlertTriage()
    event = _event(ThreatLevel.HIGH, "Potential phishing malware", {"src_ip": "203.0.113.1", "url": "http://x.io"})
    result = triage.triage(event)
    assert 0.0 <= result["triage_score"] <= 100.0


def test_auto_create_case_threshold_behavior():
    triage = AlertTriage(auto_case_threshold=CaseSeverity.HIGH)
    high = _event(ThreatLevel.HIGH, "High event", {"src_ip": "1.1.1.1"})
    low = _event(ThreatLevel.LOW, "Low event", {"src_ip": "1.1.1.2"})
    assert triage.triage(high)["auto_create_case"] is True
    assert triage.triage(low)["auto_create_case"] is False


def test_triage_batch_processes_multiple_events():
    triage = AlertTriage()
    events = [
        _event(ThreatLevel.MEDIUM, "Event 1", {"src_ip": "10.0.0.1"}),
        _event(ThreatLevel.HIGH, "Event 2", {"src_ip": "10.0.0.2"}),
    ]
    results = triage.triage_batch(events)
    assert len(results) == 2
