"""Unit tests for Layer 07 cyber SOC dataclass models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.cyber.models import (
    CaseSeverity,
    CaseStatus,
    CaseVerdict,
    EnrichmentResult,
    IncidentCase,
    MITREMapping,
    Observable,
    ObservableType,
    Playbook,
    PlaybookAction,
    PlaybookStep,
)


def test_incident_case_lifecycle_helpers():
    case = IncidentCase(
        title="SOC test incident",
        description="Test incident for Layer 07 model validation",
        severity=CaseSeverity.HIGH,
        status=CaseStatus.NEW,
    )
    payload = case.to_dict()
    assert payload["severity"] == "HIGH"
    assert case.is_open() is True
    before = len(case.timeline)
    case.add_timeline_entry("triage", "analyst-1", "Validated suspicious behavior")
    assert len(case.timeline) == before + 1
    assert case.duration_seconds() is None
    case.resolved_at = case.created_at + timedelta(minutes=5)
    assert case.duration_seconds() == 300.0


def test_case_enums_exist():
    assert CaseSeverity.CRITICAL.value == "CRITICAL"
    assert CaseStatus.ESCALATED.value == "ESCALATED"
    assert CaseVerdict.TRUE_POSITIVE.value == "TRUE_POSITIVE"


def test_observable_creation_for_all_types():
    for observable_type in ObservableType:
        observable = Observable(
            observable_type=observable_type,
            value=f"value-{observable_type.value.lower()}",
            source_case_id="case-1",
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            tags=["ioc"],
            tlp="AMBER",
        )
        assert observable.to_dict()["observable_type"] == observable_type.value


def test_enrichment_result_creation():
    enrichment = EnrichmentResult(
        analyzer="VirusTotal",
        observable_id="obs-1",
        result={"score": 10},
        verdict="malicious",
        confidence=0.9,
    )
    payload = enrichment.to_dict()
    assert payload["analyzer"] == "VirusTotal"
    assert payload["verdict"] == "malicious"


def test_mitre_mapping_keywords():
    brute = MITREMapping.from_alert("CYBER", "SSH brute force detected")
    assert brute is not None
    assert brute.technique_id == "T1110"

    sqli = MITREMapping.from_alert("WEB", "SQL injection attempt blocked")
    assert sqli is not None
    assert sqli.technique_id == "T1190"


def test_mitre_mapping_unknown():
    assert MITREMapping.from_alert("INFO", "normal heartbeat") is None


def test_playbook_and_step_creation():
    step = PlaybookStep(step_id=1, name="Notify", action=PlaybookAction.NOTIFY_ANALYST, parameters={})
    playbook = Playbook(
        playbook_id="PB-TST",
        name="Test PB",
        description="Playbook test",
        trigger_conditions=["severity >= MEDIUM"],
        steps=[step],
        mitre_techniques=["T1110"],
        tags=["test"],
    )
    assert playbook.step_count() == 1
    assert playbook.to_dict()["steps"][0]["action"] == "NOTIFY_ANALYST"
