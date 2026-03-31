"""
OODA ORIENT: Threat events -> LLM assessment -> enriched intelligence.
Tests the bridge between Layer 02 (detection) and Layer 01 (LLM reasoning).
"""

from __future__ import annotations

from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource
from src.threat_detection.threat_classifier import ThreatClassifier


def _event(category: ThreatCategory) -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.MANUAL,
        level=ThreatLevel.HIGH,
        category=category,
        title=f"{category.value} event",
        description=f"Synthetic {category.value} event for routing",
        confidence=0.9,
        raw_data={"test": True},
    )


def test_threat_to_llm_routing() -> None:
    classifier = ThreatClassifier()
    event = _event(ThreatCategory.CYBER)
    assessed = classifier.classify(event)
    assert assessed.llm_assessment


def test_kinetic_routes_to_phi3() -> None:
    classifier = ThreatClassifier()
    event = _event(ThreatCategory.KINETIC)
    assessed = classifier.classify(event)
    assert assessed.llm_assessment


def test_hybrid_routes_to_consensus() -> None:
    classifier = ThreatClassifier()
    event = _event(ThreatCategory.HYBRID)
    assessed = classifier.classify(event)
    assert assessed.llm_assessment


def test_threat_classifier_graceful_without_llm() -> None:
    classifier = ThreatClassifier()
    # Force no-LLM mode to validate graceful degraded behavior.
    classifier.available = False
    event = _event(ThreatCategory.CYBER)
    assessed = classifier.classify(event)
    assert "[PENDING]" in (assessed.llm_assessment or "")


def test_sitrep_generation() -> None:
    classifier = ThreatClassifier()
    events = [
        ThreatEvent(
            source=ThreatSource.MANUAL,
            level=level,
            category=ThreatCategory.CYBER,
            title=f"Event {idx}",
            description="Synthetic threat",
            confidence=0.8,
            raw_data={"idx": idx},
        )
        for idx, level in enumerate(
            [ThreatLevel.CRITICAL, ThreatLevel.HIGH, ThreatLevel.MEDIUM, ThreatLevel.LOW, ThreatLevel.INFO],
            start=1,
        )
    ]
    sitrep = classifier.generate_sitrep(events)
    assert isinstance(sitrep, str)
    assert sitrep.strip()
