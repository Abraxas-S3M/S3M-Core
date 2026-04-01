from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.osint_gdelt.adapter import GDELTAdapter
from packages.providers.osint_gdelt.config import GDELTConfig, SAUDI_QUERIES


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = GDELTAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "osint-gdelt"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "none"
    assert manifest.required_env_vars == []


def test_no_auth_required() -> None:
    assert GDELTAdapter(mode="airgapped").validate_credentials() is True


def test_saudi_queries_defined() -> None:
    assert len(SAUDI_QUERIES) == 10
    assert "red_sea" in SAUDI_QUERIES


def test_cameo_csv_parsing() -> None:
    adapter = GDELTAdapter(mode="airgapped")
    raw_csv = FIXTURE_DIR.joinpath("cameo_events_sample.csv").read_text(encoding="utf-8")
    parsed = adapter.normalizer.parse_cameo_csv(raw_csv)
    assert len(parsed) == 15
    assert {"SQLDATE", "Actor1Name", "EventCode", "GoldsteinScale", "ActionGeo_Lat", "ActionGeo_Long"}.issubset(parsed[0].keys())


def test_cameo_country_filter() -> None:
    adapter = GDELTAdapter(mode="airgapped")
    result = adapter.fetch_cameo_events(country_codes=["YE"])
    assert result["count"] == 3
    assert all(item["ActionGeo_CountryCode"] == "YE" for item in result["events"])


def test_cameo_code_filter() -> None:
    adapter = GDELTAdapter(mode="airgapped")
    raw_csv = FIXTURE_DIR.joinpath("cameo_events_sample.csv").read_text(encoding="utf-8")
    only_19 = adapter.normalizer.parse_cameo_csv(raw_csv, filter_codes=["19"])
    assert len(only_19) == 3
    assert all(str(item["EventCode"]).startswith("19") for item in only_19)


def test_normalize_article_tone() -> None:
    article = {
        "url": "https://example.com/story",
        "title": "Example",
        "seendate": "2026-03-21T10:00:00Z",
        "sourcecountry": "SA",
        "language": "en",
        "tone": -50,
    }
    normalized = GDELTAdapter(mode="airgapped").normalizer.normalize_article(article)
    assert normalized.sentiment_score == -0.5


def test_normalize_cameo_event_type() -> None:
    raw_csv = FIXTURE_DIR.joinpath("cameo_events_sample.csv").read_text(encoding="utf-8")
    adapter = GDELTAdapter(mode="airgapped")
    records = adapter.normalizer.parse_cameo_csv(raw_csv, filter_codes=["194"])
    normalized = adapter.normalizer.normalize_cameo_event(records[0])
    assert normalized.event_type == "conflict"


def test_goldstein_severity() -> None:
    severity = GDELTAdapter(mode="airgapped").normalizer.severity_from_goldstein(-7.5)
    assert severity == "critical"


def test_confidence_from_mentions() -> None:
    raw_csv = FIXTURE_DIR.joinpath("cameo_events_sample.csv").read_text(encoding="utf-8")
    adapter = GDELTAdapter(mode="airgapped")
    records = adapter.normalizer.parse_cameo_csv(raw_csv, filter_codes=["194"])
    normalized = adapter.normalizer.normalize_cameo_event(records[0])
    assert normalized.provenance.confidence == 0.9


def test_mena_country_codes() -> None:
    cfg = GDELTConfig()
    assert len(cfg.mena_country_codes) == 16
    for country in ["SA", "YE", "IR", "IQ", "DJ", "SO"]:
        assert country in cfg.mena_country_codes


def test_fetch_airgapped() -> None:
    data = GDELTAdapter(mode="airgapped").fetch_cameo_events(country_codes=["YE", "IR"])
    assert data["count"] == 6
