from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.osint_mediacloud.adapter import MediaCloudAdapter
from packages.providers.osint_mediacloud.normalizer import MediaCloudNormalizer


def test_manifest_correct() -> None:
    manifest = MediaCloudAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "osint-mediacloud"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "api_key"
    assert manifest.rate_limit_rpm == 40


def test_normalize_story_type() -> None:
    adapter = MediaCloudAdapter(mode="airgapped")
    story = adapter.fetch_stories("gulf security", days_back=7, limit=1)["stories"][0]
    event = adapter.normalizer.normalize_story(story)
    assert event.event_type == "media_report"


def test_narrative_surge_detection() -> None:
    adapter = MediaCloudAdapter(mode="airgapped")
    counts = adapter.fetch_story_count_timeseries("yemen houthi", days_back=30)["counts"]
    surges = adapter.normalizer.detect_narrative_surge(counts, query="yemen houthi", threshold_multiplier=3.0)
    assert any(item["date"] == "2026-03-12" for item in surges)


def test_surge_no_false_positive() -> None:
    n = MediaCloudNormalizer()
    counts = [{"date": f"2026-03-{idx:02d}", "count": 100 + idx} for idx in range(1, 15)]
    surges = n.detect_narrative_surge(counts, query="steady topic", threshold_multiplier=3.0)
    assert surges == []


def test_arabic_english_comparison_structure() -> None:
    data = MediaCloudAdapter(mode="airgapped").compare_arabic_english("saudi defense", days_back=7)
    assert {"arabic", "english", "coverage_ratio"}.issubset(data.keys())


def test_trend_change_pct_computed() -> None:
    counts = MediaCloudAdapter(mode="airgapped").fetch_story_count_timeseries("yemen houthi", days_back=30)["counts"]
    trend = MediaCloudAdapter(mode="airgapped").normalizer.normalize_trend(counts)
    assert "change_pct" in trend[1]


def test_fetch_airgapped() -> None:
    data = MediaCloudAdapter(mode="airgapped").fetch({"action": "stories", "query": "gulf"})
    assert "stories" in data and len(data["stories"]) > 0
