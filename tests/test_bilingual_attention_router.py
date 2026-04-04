from src.llm_core.bilingual_attention_router import (
    BilingualAttentionRouter,
    Language,
    RoutingDecision,
)


def test_classify_char_handles_arabic_digits_punctuation_and_tashkeel():
    """Validate Unicode script classification for mixed tactical message symbols."""
    router = BilingualAttentionRouter()
    assert router._classify_char("ا") == Language.ARABIC
    assert router._classify_char("َ") == Language.ARABIC
    assert router._classify_char("A") == Language.ENGLISH
    assert router._classify_char("١") == Language.UNKNOWN
    assert router._classify_char("،") == Language.UNKNOWN


def test_detect_language_segments_preserves_text_and_detects_both_languages():
    """Ensure segmentation keeps full payload while finding Arabic/English spans."""
    router = BilingualAttentionRouter()
    text = "تَقرير الحالة: patrol sector ٧ completed، تم رصد ٣ vehicles"
    segments = router.detect_language_segments(text)
    rebuilt = "".join(segment.text for segment in segments)

    assert rebuilt == text
    assert any(segment.language == Language.ARABIC for segment in segments)
    assert any(segment.language == Language.ENGLISH for segment in segments)
    assert "تَقرير" in rebuilt
    assert "٧" in rebuilt and "٣" in rebuilt


def test_make_routing_decision_arabic_majority_uses_arabic_engine():
    """Arabic-heavy command traffic should route to Arabic-specialized engine."""
    router = BilingualAttentionRouter(arabic_engine_id="arabic-x", english_engine_id="english-y")
    text = "تقرير الحالة تم رصد هدف قرب القطاع north checkpoint"
    decision = router.make_routing_decision(text)

    assert decision.strategy == "single_allam"
    assert decision.primary_engine == "arabic-x"
    assert "north checkpoint" in decision.context_hints.get("minority_segments", "")


def test_make_routing_decision_english_majority_uses_english_engine():
    """English-heavy tactical brief should route to English-specialized engine."""
    router = BilingualAttentionRouter(arabic_engine_id="arabic-x", english_engine_id="english-y")
    text = "patrol team moving to sector seven with overwatch قرب القاعدة"
    decision = router.make_routing_decision(text)

    assert decision.strategy == "single_phi3"
    assert decision.primary_engine == "english-y"
    assert decision.context_hints.get("transliteration_hints")


def test_make_routing_decision_mixed_uses_parallel_fusion():
    """Balanced bilingual traffic should use parallel routing + fusion."""
    router = BilingualAttentionRouter(arabic_engine_id="arabic-x", english_engine_id="english-y")
    text = "تقرير الحالة patrol sector تم الرصد completed بنجاح"
    decision = router.make_routing_decision(text)

    assert decision.strategy == "parallel_fuse"
    assert decision.primary_engine in {"arabic-x", "english-y"}
    assert decision.secondary_engine in {"arabic-x", "english-y"}
    assert decision.primary_engine != decision.secondary_engine


def test_fuse_responses_falls_back_to_best_single_response_when_low_coherence():
    """Low-coherence fused draft should fall back to the safer single engine output."""
    router = BilingualAttentionRouter(arabic_engine_id="arabic-x", english_engine_id="english-y")
    routing = RoutingDecision(
        strategy="parallel_fuse",
        primary_engine="arabic-x",
        secondary_engine="english-y",
        arabic_fraction=0.4,
        english_fraction=0.6,
        segments=[],
        context_hints={},
    )

    arabic_response = "aبcدeوfز"
    english_response = "Sector seven secured with no hostile contact."
    fused = router.fuse_responses(arabic_response, english_response, routing)

    assert fused.text == english_response
    assert fused.primary_source == "english-y"
    assert 0.0 <= fused.coherence_score <= 1.0
