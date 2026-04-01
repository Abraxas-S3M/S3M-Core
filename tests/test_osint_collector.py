from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.apps.intel.osint.osint_collector import OSINTCollector


def _seed_watch_dir(path: Path) -> None:
    rows = [
        {
            "title": "Saudi military patrol increased near Hormuz",
            "content": "Security alert after suspicious vessel behavior.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": "offline://collector/1",
            "region": "Strait of Hormuz",
            "topic": "maritime_security",
        },
        {
            "title": "Routine diplomatic exchange",
            "content": "Officials discuss de-escalation steps.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": "offline://collector/2",
            "region": "Arabian Peninsula",
            "topic": "diplomacy",
        },
    ]
    (path / "collector.json").write_text(json.dumps(rows), encoding="utf-8")


def test_collect_processes_watch_directory(tmp_path: Path):
    watch = tmp_path / "incoming"
    watch.mkdir(parents=True, exist_ok=True)
    _seed_watch_dir(watch)
    collector = OSINTCollector()
    collector.ingester.watch_dir = str(watch)
    result = collector.collect()
    assert result["items_collected"] >= 2
    assert isinstance(result["sources_used"], list)


def test_get_high_priority_items_filters_by_threshold(tmp_path: Path):
    watch = tmp_path / "incoming"
    watch.mkdir(parents=True, exist_ok=True)
    _seed_watch_dir(watch)
    collector = OSINTCollector()
    collector.ingester.watch_dir = str(watch)
    collector.collect()
    highs = collector.get_high_priority_items(threshold=0.5)
    assert all(item.relevance_score >= 0.5 for item in highs)


def test_search_finds_items_by_keyword(tmp_path: Path):
    watch = tmp_path / "incoming"
    watch.mkdir(parents=True, exist_ok=True)
    _seed_watch_dir(watch)
    collector = OSINTCollector()
    collector.ingester.watch_dir = str(watch)
    collector.collect()
    result = collector.search("Hormuz")
    assert any("Hormuz" in item.title for item in result)
