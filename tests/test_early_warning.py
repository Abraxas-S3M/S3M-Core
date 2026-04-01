from __future__ import annotations

from datetime import datetime, timezone

from src.apps.intel.models import OSINTItem
from src.apps.intel.monitoring.early_warning import EarlyWarningSystem


def _item(region: str, topic: str, sentiment: str) -> OSINTItem:
    return OSINTItem(
        item_id=f"i-{region[:2]}-{sentiment}",
        source_id="src-1",
        timestamp=datetime.now(timezone.utc),
        title=f"{sentiment} update",
        content=f"{sentiment} event in {region}",
        language="en",
        url=None,
        regions=[region],
        topics=[topic],
        entities=[],
        sentiment=sentiment,
        relevance_score=0.8,
        summary=None,
        credibility="possible",
    )


def test_create_default_indicators_returns_eight():
    ew = EarlyWarningSystem()
    indicators = ew.create_default_indicators()
    assert len(indicators) == 8


def test_is_triggered_true_when_value_exceeds_threshold():
    ew = EarlyWarningSystem()
    ind = ew.create_indicator("Test", "Desc", "Region", "topic", threshold=50)
    ew.update_indicator(ind.indicator_id, 60, "test")
    assert ind.is_triggered() is True


def test_auto_update_from_items_increases_for_alarming():
    ew = EarlyWarningSystem()
    ind = ew.create_indicator("Drone/UAV Threat Level", "Desc", "all regions", "drone_threats", threshold=55)
    items = [_item("Red Sea", "drone_threats", "alarming") for _ in range(5)]
    ew.auto_update_from_items(items)
    assert ind.current_value >= 15


def test_decay_reduces_values_over_time():
    ew = EarlyWarningSystem()
    ind = ew.create_indicator("Decay Test", "Desc", "all regions", "drone_threats", threshold=90)
    ew.update_indicator(ind.indicator_id, 30, "set")
    ew._last_auto_update = datetime.now(timezone.utc).replace(year=2024)
    ew.auto_update_from_items([])
    assert ind.current_value < 30


def test_get_active_warnings_only_triggered():
    ew = EarlyWarningSystem()
    ind_a = ew.create_indicator("A", "Desc", "Region", "topic", threshold=50)
    ind_b = ew.create_indicator("B", "Desc", "Region", "topic", threshold=90)
    ew.update_indicator(ind_a.indicator_id, 70, "raise")
    ew.update_indicator(ind_b.indicator_id, 40, "remain")
    active = ew.get_active_warnings()
    assert [i.name for i in active] == ["A"]
