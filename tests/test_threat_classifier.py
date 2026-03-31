"""Tests for ThreatClassifier routing and fallback behavior."""

from __future__ import annotations

from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource
from src.threat_detection.threat_classifier import ThreatClassifier


def _event(category: ThreatCategory) -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.MEDIUM,
        category=category,
        title="Classifier test event",
        description="Validate domain routing mapping.",
        raw_data={"test": True},
        confidence=0.8,
    )


def test_routing_map_by_category():
    classifier = ThreatClassifier()
    if not classifier.available:
        # In fallback mode this mapping method returns None by design.
        assert classifier._resolve_domain(ThreatCategory.CYBER) is None
        return

    assert classifier._resolve_domain(ThreatCategory.CYBER).value == "reasoning"
    assert classifier._resolve_domain(ThreatCategory.KINETIC).value == "tactical"
    assert classifier._resolve_domain(ThreatCategory.ELECTRONIC_WARFARE).value == "reasoning"
    assert classifier._resolve_domain(ThreatCategory.SURVEILLANCE).value == "planning"
    assert classifier._resolve_domain(ThreatCategory.HYBRID).value == "consensus"


def test_generate_sitrep_format():
    classifier = ThreatClassifier()
    events = [_event(ThreatCategory.CYBER), _event(ThreatCategory.KINETIC)]
    sitrep = classifier.generate_sitrep(events)
    assert isinstance(sitrep, str)
    assert sitrep


def test_graceful_fallback_when_unavailable(monkeypatch):
    classifier = ThreatClassifier()
    monkeypatch.setattr(classifier, "available", False)
    monkeypatch.setattr(classifier, "_orchestrator", None)

    event = _event(ThreatCategory.CYBER)
    out = classifier.classify(event)
    assert out.llm_assessment is not None
    assert out.llm_assessment.startswith("[PENDING]")
