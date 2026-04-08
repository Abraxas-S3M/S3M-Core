from __future__ import annotations

from datetime import datetime, timezone

from src.apps.intel.models import OSINTItem
from src.apps.intel.osint.analyzer import OSINTAnalyzer


def _item(source_id: str, title: str, content: str) -> OSINTItem:
    return OSINTItem(
        item_id=f"item-{source_id}-{abs(hash(title)) % 100000}",
        source_id=source_id,
        timestamp=datetime.now(timezone.utc),
        title=title,
        content=content,
        language="auto",
        url=None,
        regions=["Red Sea"],
        topics=["regional_stability"],
        entities=[],
    )


def test_analyze_extracts_entities_english() -> None:
    analyzer = OSINTAnalyzer()
    item = _item("s1", "Military update", "The 3rd Marine Division moved Patriot units near Bab el-Mandeb.")
    out = analyzer.analyze(item)
    values = {ent["value"] for ent in out.entities}
    assert any("3rd Marine Division" in value for value in values)
    assert any("Patriot" in value for value in values)


def test_analyze_extracts_entities_arabic() -> None:
    analyzer = OSINTAnalyzer()
    item = _item("s1", "تحديث عسكري", "تحركت الفرقة الثالثة قرب باب المندب مع منظومة دفاع.")
    out = analyzer.analyze(item)
    assert out.language == "ar"
    assert len(out.entities) >= 1


def test_sentiment_attack_launched_alarming() -> None:
    analyzer = OSINTAnalyzer()
    item = _item("s1", "Alert", "An attack launched against a convoy.")
    out = analyzer.analyze(item)
    assert out.sentiment == "alarming"


def test_sentiment_peace_agreement_positive() -> None:
    analyzer = OSINTAnalyzer()
    item = _item("s1", "Diplomacy", "A peace agreement signed by regional parties.")
    out = analyzer.analyze(item)
    assert out.sentiment == "positive"


def test_cross_reference_matching_entities_different_sources() -> None:
    analyzer = OSINTAnalyzer()
    item1 = analyzer.analyze(
        _item("src-a", "Hormuz update", "Patriot unit deployed near Strait of Hormuz.")
    )
    item2 = analyzer.analyze(
        _item("src-b", "Second report", "Strait of Hormuz sees Patriot movement.")
    )
    refs = analyzer.cross_reference([item1, item2])
    assert refs
    assert any("patriot" in row["entity"] or "strait of hormuz" in row["entity"] for row in refs)


def test_semantic_cross_reference_links_related_items() -> None:
    analyzer = OSINTAnalyzer()
    item1 = _item("src-a", "Hormuz patrol", "Patriot convoy repositioned near Strait of Hormuz.")
    item2 = _item("src-b", "Maritime alert", "Strait of Hormuz reports Patriot convoy movement.")
    item3 = _item("src-c", "Cyber bulletin", "Credential phishing campaign targeted mail gateways.")
    linked = analyzer.semantic_cross_reference([item1, item2, item3], top_k=3)
    assert linked
    pairs = {(row["item_a"], row["item_b"]) for row in linked}
    assert any(item1.item_id in pair and item2.item_id in pair for pair in pairs)
