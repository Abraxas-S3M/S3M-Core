from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.pipelines.geoint.geoint_pipeline import GEOINTIngestionPipeline


def test_ingest_all_merges_providers() -> None:
    result = GEOINTIngestionPipeline().ingest_all("persian_gulf", 7)
    assert result["total_observations"] > 0
    assert len(result["by_provider"]) == 4


def test_deduplication_works() -> None:
    result = GEOINTIngestionPipeline().ingest_all("persian_gulf", 7)
    assert result["deduplicated"] >= 1


def test_ingest_sar_maritime_filters_sar_only() -> None:
    result = GEOINTIngestionPipeline().ingest_sar_maritime("persian_gulf", 3)
    assert result["count"] > 0
    assert all(item["observation_type"] == "sar" for item in result["observations"])


def test_ingest_fires_returns_thermal() -> None:
    result = GEOINTIngestionPipeline().ingest_fires("full_saudi", 1)
    assert result["count"] > 0
    assert all(item["observation_type"] == "thermal" for item in result["observations"])


def test_coverage_report_structure() -> None:
    report = GEOINTIngestionPipeline().get_coverage_report("persian_gulf", 30)
    assert "providers" in report
    assert len(report["providers"]) == 4


def test_health_check_reports_all_providers() -> None:
    health = GEOINTIngestionPipeline().health_check()
    assert set(health["providers"].keys()) == {"geoint-copernicus", "geoint-sentinelhub", "geoint-nasa-earthdata", "geoint-gee"}
