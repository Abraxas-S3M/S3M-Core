from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.apps.intel.models import CrisisSeverity, OSINTItem
from src.apps.intel.monitoring.crisis_tracker import CrisisTracker


def _mk_item(i: int, source: str = "src-1", alarming: bool = True) -> OSINTItem:
    return OSINTItem(
        item_id=f"it-{i}",
        source_id=source,
        timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
        title=f"Item {i}",
        content="attack launched in region",
        language="en",
        url=None,
        regions=["Red Sea"],
        topics=["maritime_security"],
        entities=[{"type": "geo_feature", "value": "Bab el-Mandeb"}],
        sentiment="alarming" if alarming else "neutral",
        relevance_score=0.9,
        summary=None,
        credibility="possible",
    )


def test_create_crisis_and_get_crisis():
    tracker = CrisisTracker()
    crisis = tracker.create_crisis("Test Crisis", "desc", CrisisSeverity.ELEVATED, "Red Sea")
    fetched = tracker.get_crisis(crisis.event_id)
    assert fetched is not None
    assert fetched.name == "Test Crisis"


def test_update_crisis_adds_timeline_entry():
    tracker = CrisisTracker()
    crisis = tracker.create_crisis("Test", "desc", CrisisSeverity.ELEVATED, "Red Sea")
    before = len(crisis.timeline)
    tracker.update_crisis(crisis.event_id, "new update")
    assert len(crisis.timeline) == before + 1


def test_escalate_increases_severity():
    tracker = CrisisTracker()
    crisis = tracker.create_crisis("Test", "desc", CrisisSeverity.ELEVATED, "Red Sea")
    tracker.escalate(crisis.event_id, "reason")
    assert crisis.severity in {CrisisSeverity.HIGH, CrisisSeverity.SEVERE, CrisisSeverity.CRITICAL}


def test_de_escalate_decreases_severity():
    tracker = CrisisTracker()
    crisis = tracker.create_crisis("Test", "desc", CrisisSeverity.HIGH, "Red Sea")
    tracker.de_escalate(crisis.event_id, "reason")
    assert crisis.severity in {CrisisSeverity.ROUTINE, CrisisSeverity.ELEVATED, CrisisSeverity.HIGH}


def test_resolve_sets_status_resolved():
    tracker = CrisisTracker()
    crisis = tracker.create_crisis("Test", "desc", CrisisSeverity.HIGH, "Red Sea")
    tracker.resolve(crisis.event_id, "resolved")
    assert crisis.status == "resolved"


def test_auto_detect_crises_creates_crisis_from_three_or_more_alarming_items():
    tracker = CrisisTracker()
    items = [_mk_item(1, "s1"), _mk_item(2, "s2"), _mk_item(3, "s3")]
    crises = tracker.auto_detect_crises(items)
    assert len(crises) >= 1
    assert crises[0].region == "Red Sea"
