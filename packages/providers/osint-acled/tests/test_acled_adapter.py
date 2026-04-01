from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.osint_acled.adapter import ACLEDAdapter
from packages.providers.osint_acled.normalizer import ACLEDNormalizer


def test_manifest_correct() -> None:
    manifest = ACLEDAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "osint-acled"
    assert manifest.tier == "FREE"
    assert manifest.auth_type == "api_key"


def test_event_type_mapping() -> None:
    normalizer = ACLEDNormalizer()
    assert normalizer._event_type_map["Battles"] == "conflict"
    assert normalizer._event_type_map["Protests"] == "protest"


def test_fatality_severity() -> None:
    n = ACLEDNormalizer()
    assert n.compute_severity({"fatalities": 42, "event_type": "Battles"}) == "critical"
    assert n.compute_severity({"fatalities": 8, "event_type": "Battles"}) == "high"
    assert n.compute_severity({"fatalities": 3, "event_type": "Battles"}) == "medium"


def test_confidence_from_geo_precision() -> None:
    n = ACLEDNormalizer()
    event = {"data_id": "x", "event_date": "2026-03-20", "event_type": "Battles", "country": "Yemen", "geo_precision": 1}
    normalized = n.normalize_event(event)
    assert normalized.provenance.confidence == 0.95


def test_normalize_has_fatalities() -> None:
    event = ACLEDAdapter(mode="airgapped").fetch_saudi_region(days_back=30)["data"][0]
    normalized = ACLEDAdapter(mode="airgapped").normalize({"data": [event]})[0]
    assert normalized.fatalities is not None


def test_normalize_has_actors() -> None:
    event = ACLEDAdapter(mode="airgapped").fetch_saudi_region(days_back=30)["data"][0]
    normalized = ACLEDAdapter(mode="airgapped").normalize({"data": [event]})[0]
    assert len(normalized.actors) >= 1


def test_extract_conflict_actors() -> None:
    events = ACLEDAdapter(mode="airgapped").fetch_saudi_region(days_back=30)["data"]
    actors = ACLEDNormalizer().extract_conflict_actors(events)
    assert len(actors) >= 3
    assert {"actor", "event_count", "fatalities_total"}.issubset(actors[0].keys())


def test_16_countries() -> None:
    cfg = ACLEDAdapter(mode="airgapped").config
    assert len(cfg.saudi_relevant_countries) == 16
    for code in ["Saudi Arabia", "Yemen", "Oman", "Iraq", "Iran", "Djibouti"]:
        assert code in cfg.saudi_relevant_countries


def test_fetch_airgapped() -> None:
    data = ACLEDAdapter(mode="airgapped").fetch_saudi_region(days_back=30)
    assert data["count"] == 14
