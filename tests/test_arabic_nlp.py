#!/usr/bin/env python3
"""Tests for Arabic NLP engine in Layer 08."""

from __future__ import annotations

from services.comms.models import MessagePriority
from services.comms.nlp import ArabicNLPEngine


def test_language_detection_arabic_text() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    summary = engine.summarize("نحتاج دعم جوي فوري في القطاع الشمالي")
    assert summary.original_language == "ar"


def test_language_detection_english_text() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    summary = engine.summarize("Enemy contact near ridge line")
    assert summary.original_language == "en"


def test_extract_entities_finds_grid_reference() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    entities = engine.extract_entities("Observed movement at 500123, 400987.")
    assert any(e["type"] == "location" and "500123" in e["value"] for e in entities)


def test_extract_entities_finds_callsign() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    entities = engine.extract_entities("EAGLE-01 reports clear route.")
    assert any(e["type"] == "unit" and e["value"] == "EAGLE-01" for e in entities)


def test_classify_intent_request_support_english() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    intent = engine.classify_intent("Request support at checkpoint bravo.")
    assert intent == "request_support"


def test_classify_intent_request_support_arabic() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    intent = engine.classify_intent("نحتاج دعم الآن في هذا القطاع")
    assert intent == "request_support"


def test_score_urgency_flash_near_one() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    score = engine.score_urgency("Immediate action required!", priority=MessagePriority.FLASH)
    assert score >= 0.95


def test_score_urgency_deferred_near_point_one() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    score = engine.score_urgency("Routine logistics update.", priority=MessagePriority.DEFERRED)
    assert 0.09 <= score <= 0.2


def test_summarize_returns_summary_object_with_keyword_fallback() -> None:
    engine = ArabicNLPEngine(model_backend="keyword")
    summary = engine.summarize("This is a test tactical message for summary fallback.")
    assert summary.message_id
    assert summary.summary_en or summary.summary_ar
    assert isinstance(summary.entities, list)
