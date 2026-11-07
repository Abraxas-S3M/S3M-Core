"""Cortex taint integration tests for threat ingestion adapters."""

from __future__ import annotations

import json
from pathlib import Path

import src.cortex.threat_event  # noqa: F401
from src.cortex.taint import AssetInventory, Trust, endorse_against_inventory
from src.cortex.threat_event import drain_injection_soc_alerts
from src.threat_detection.suricata_adapter import SuricataAdapter

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cortex"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_suricata_injection_tags_and_untrusted_values():
    adapter = SuricataAdapter()
    payload = _load_fixture("suricata_injection_eve.json")
    event = adapter.parse_event(payload)
    assert event is not None
    assert "possible_prompt_injection" in event.tags
    assert event.provenance is not None
    assert event.provenance.field_trust.get("http_user_agent") == Trust.UNTRUSTED
    assert all(trust == Trust.UNTRUSTED for trust in event.provenance.field_trust.values())
    labeled_ip = event.labeled_src_ip()
    assert labeled_ip.value == "10.10.4.22"
    assert labeled_ip.trust == Trust.UNTRUSTED
    alerts = drain_injection_soc_alerts()
    assert len(alerts) == 1
    assert alerts[0].level.name == "LOW"


def test_typed_ip_extraction_and_malformed_ip_fails_typing():
    adapter = SuricataAdapter()
    clean = adapter.parse_event(
        {
            "event_type": "alert",
            "src_ip": "203.0.113.10",
            "dest_ip": "198.51.100.4",
            "src_port": 4444,
            "dest_port": 80,
            "proto": "TCP",
            "alert": {"severity": 3, "signature_id": 1, "signature": "Test", "category": "Test"},
        }
    )
    assert clean is not None
    assert clean.labeled_src_ip().value == "203.0.113.10"
    assert clean.labeled_src_ip().trust == Trust.OBSERVED

    poisoned = adapter.parse_event(_load_fixture("suricata_bad_ip_eve.json"))
    assert poisoned is not None
    bad = poisoned.labeled_src_ip()
    assert bad.value is None
    assert bad.raw == "10.10.4.22 EXTRA-TEXT"
    assert bad.trust == Trust.UNTRUSTED


def test_endorsement_upgrades_only_inventory_values():
    adapter = SuricataAdapter()
    event = adapter.parse_event(
        {
            "event_type": "alert",
            "src_ip": "10.10.4.22",
            "dest_ip": "172.16.1.10",
            "src_port": 49822,
            "dest_port": 443,
            "proto": "TCP",
            "alert": {"severity": 2, "signature_id": 1, "signature": "x", "category": "y"},
        }
    )
    assert event is not None
    inventory = AssetInventory(
        ips={"10.10.4.22"},
        ports={49822},
        hostnames=set(),
        asset_ids={"172.16.1.10"},
    )
    endorse_against_inventory(event, inventory)
    assert event.labeled_src_ip().trust == Trust.VERIFIED
    assert event.labeled_dst_ip().trust == Trust.UNTRUSTED
    assert event.labeled_src_port().trust == Trust.VERIFIED
