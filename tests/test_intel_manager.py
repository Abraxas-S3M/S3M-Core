from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.apps.intel import IntelManager


def _seed(manager: IntelManager) -> None:
    manager.collector.source_manager.create_default_sources()
    manager.monitor.early_warning.create_default_indicators()
    src_id = manager.collector.source_manager.get_sources()[0].source_id
    path = Path(manager.collector.ingester.watch_dir) / "manager_seed.json"
    payload = [
        {
            "title": "Saudi maritime patrol update",
            "content": "Saudi Arabia naval security patrol monitors drone activity.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": "offline://manager/1",
            "region": "Red Sea",
            "topic": "drone_threats",
        }
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    manager.collector.ingester.ingest_file(str(path), src_id)
    manager.collector._items = manager.collector.ingester.items


def test_collect_and_analyze_runs_full_pipeline():
    manager = IntelManager()
    _seed(manager)
    result = manager.collect_and_analyze()
    assert "collection" in result
    assert "monitoring" in result


def test_generate_daily_brief_returns_dailybrief():
    manager = IntelManager()
    _seed(manager)
    brief = manager.generate_daily_brief()
    assert brief.brief_id


def test_generate_sitrep_returns_bilingual_intel_report():
    manager = IntelManager()
    _seed(manager)
    report = manager.generate_sitrep("Red Sea")
    assert report.body_en
    assert report.body_ar


def test_search_intel_returns_matching_items():
    manager = IntelManager()
    _seed(manager)
    items = manager.search_intel("Saudi")
    assert len(items) >= 1


def test_get_crises_returns_active_crises():
    manager = IntelManager()
    crisis = manager.monitor.crisis_tracker.create_crisis(
        name="Test Crisis",
        description="desc",
        severity="HIGH",
        region="Red Sea",
    )
    crises = manager.get_crises()
    assert any(c.event_id == crisis.event_id for c in crises)


def test_health_check_returns_subsystem_statuses():
    manager = IntelManager()
    health = manager.health_check()
    assert set(["collector", "monitor", "briefings", "dashboard"]).issubset(health.keys())
