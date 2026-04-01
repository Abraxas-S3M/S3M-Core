from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.osint_intelligencex.adapter import IntelligenceXAdapter
from packages.providers.osint_intelligencex.config import IntelligenceXConfig


def test_manifest_correct() -> None:
    manifest = IntelligenceXAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "osint-intelligencex"
    assert manifest.tier == "FREEMIUM"
    assert manifest.auth_type == "api_key"
    assert manifest.rate_limit_rpm == 3


def test_bucket_type_mapping() -> None:
    normalizer = IntelligenceXAdapter(mode="airgapped").normalizer
    assert normalizer._event_type_from_bucket("pastes") == "data_leak"
    assert normalizer._event_type_from_bucket("darknet") == "darknet_activity"
    assert normalizer._event_type_from_bucket("whois") == "infrastructure_change"


def test_leak_severity() -> None:
    normalizer = IntelligenceXAdapter(mode="airgapped").normalizer
    assert normalizer.classify_leak_severity({"bucket": "darknet", "size": 10 * 1024 * 1024}) == "critical"
    assert normalizer.classify_leak_severity({"bucket": "pastes", "name": "contains credentials"}) == "high"


def test_normalize_record_sentiment() -> None:
    normalizer = IntelligenceXAdapter(mode="airgapped").normalizer
    darknet = normalizer.normalize_record({"bucket": "darknet", "systemid": "a", "name": "x", "date": "2026-03-20T00:00:00Z", "media": 2})
    whois = normalizer.normalize_record({"bucket": "whois", "systemid": "b", "name": "y", "date": "2026-03-20T00:00:00Z", "media": 3})
    assert darknet.sentiment_score == -0.8
    assert whois.sentiment_score == -0.2


def test_normalize_confidence_by_bucket() -> None:
    normalizer = IntelligenceXAdapter(mode="airgapped").normalizer
    whois = normalizer.normalize_record({"bucket": "whois", "systemid": "1", "name": "w", "date": "2026-03-20T00:00:00Z", "media": 3})
    darknet = normalizer.normalize_record({"bucket": "darknet", "systemid": "2", "name": "d", "date": "2026-03-20T00:00:00Z", "media": 2})
    assert whois.provenance.confidence == 0.9
    assert darknet.provenance.confidence == 0.5


def test_phonebook_normalization() -> None:
    selectors = [
        {"selectorvalue": "ops@aramco.com", "type": "email", "sources": 4},
        {"selectorvalue": "vpn.aramco.com", "type": "domain", "sources": 2},
    ]
    normalized = IntelligenceXAdapter(mode="airgapped").normalizer.normalize_phonebook(selectors)
    assert normalized[0]["type"] == "email"
    assert normalized[0]["value"] == "ops@aramco.com"
    assert normalized[0]["sources"] == 4


def test_saudi_search_terms() -> None:
    cfg = IntelligenceXConfig()
    assert len(cfg.saudi_search_terms) == 7


def test_poll_mechanism() -> None:
    adapter = IntelligenceXAdapter(mode="airgapped")
    output = adapter.search("aramco.com")
    assert output["count"] == 10
    assert output["search_id"] == "fixture-search-aramco"


def test_fetch_airgapped() -> None:
    payload = IntelligenceXAdapter(mode="airgapped").fetch({"action": "search", "term": "aramco.com"})
    assert payload["count"] == 10
