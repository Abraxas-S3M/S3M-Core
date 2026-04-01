from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.pipelines.osint.osint_pipeline import OSINTFusionPipeline


def test_ingest_all_merges_providers() -> None:
    result = OSINTFusionPipeline().ingest_all(days_back=1)
    assert result["total_events"] > 0
    assert set(result["by_provider"].keys()) == {"osint-gdelt", "osint-acled", "osint-mediacloud", "osint-intelligencex"}


def test_dedup_gdelt_acled_match() -> None:
    pipeline = OSINTFusionPipeline()
    result = pipeline.ingest_conflict_events(region="all", days_back=7)
    merged = [item for item in result["events"] if item.get("provider_id") == "merged-acled-gdelt"]
    assert len(merged) >= 1
    assert any(item.get("fatalities") is not None for item in merged)
    assert any(item.get("metadata", {}).get("gdelt_media_mentions", 0) >= 1 for item in merged)


def test_dedup_proximity() -> None:
    result = OSINTFusionPipeline().ingest_conflict_events(region="all", days_back=7)
    assert result["deduplicated"] >= 1


def test_conflict_events_has_fatalities() -> None:
    result = OSINTFusionPipeline().ingest_conflict_events(region="all", days_back=7)
    assert any(item.get("fatalities") is not None for item in result["events"])


def test_media_landscape_has_trend() -> None:
    result = OSINTFusionPipeline().ingest_media_landscape("yemen houthi", days_back=30)
    assert result["total_articles"] > 0
    assert len(result["daily_trend"]) > 0
    assert any(item.get("surge") for item in result["daily_trend"])


def test_dark_osint_classified() -> None:
    result = OSINTFusionPipeline().ingest_dark_osint(days_back=7)
    assert result["leaks_found"] >= 1
    assert len(result["critical_findings"]) >= 1


def test_feed_to_early_warning_updates_indicators() -> None:
    pipeline = OSINTFusionPipeline()
    events = pipeline.ingest_conflict_events(region="all", days_back=7)["events"]
    updates = pipeline.feed_to_early_warning(events)
    assert "Yemen Escalation" in updates
    assert updates["Yemen Escalation"] >= 1


def test_feed_to_briefing_generator() -> None:
    pipeline = OSINTFusionPipeline()
    events = pipeline.ingest_all(days_back=1)
    items = pipeline.feed_to_briefing_generator(pipeline._last_events)  # noqa: SLF001
    assert len(items) > 0
    assert all(item["source"] == "OSINT" for item in items)


def test_regional_summary_structure() -> None:
    pipeline = OSINTFusionPipeline()
    pipeline.ingest_all(days_back=1)
    summary = pipeline.get_regional_summary()
    assert len(summary["regions"]) == 8
    assert "Arabian Peninsula" in summary["regions"]


def test_health_check_all_providers() -> None:
    health = OSINTFusionPipeline().health_check()
    assert set(health["providers"].keys()) == {"osint-gdelt", "osint-acled", "osint-mediacloud", "osint-intelligencex"}
