"""Tests for SuricataAdapter parsing and severity/category mapping."""

from __future__ import annotations

import json
from pathlib import Path

from src.threat_detection.models import ThreatCategory, ThreatLevel
from src.threat_detection.suricata_adapter import SuricataAdapter


def _sample_alert_event() -> dict:
    return {
        "timestamp": "2026-03-31T10:30:45.123456+00:00",
        "event_type": "alert",
        "src_ip": "10.10.4.22",
        "src_port": 49822,
        "dest_ip": "172.16.1.10",
        "dest_port": 443,
        "proto": "TCP",
        "alert": {
            "severity": 2,
            "signature_id": 2019236,
            "signature": "ET TROJAN Possible Malware CnC Check-in",
            "category": "A Network Trojan was detected",
        },
    }


def test_parse_event_from_sample_alert():
    adapter = SuricataAdapter()
    event = adapter.parse_event(_sample_alert_event())
    assert event is not None
    assert event.level == ThreatLevel.HIGH
    assert event.category == ThreatCategory.CYBER
    assert "10.10.4.22" in event.description


def test_suricata_severity_mapping():
    adapter = SuricataAdapter()
    assert adapter._map_severity(1) == ThreatLevel.CRITICAL
    assert adapter._map_severity(2) == ThreatLevel.HIGH
    assert adapter._map_severity(3) == ThreatLevel.MEDIUM
    assert adapter._map_severity(4) == ThreatLevel.LOW


def test_suricata_category_mapping():
    adapter = SuricataAdapter()
    assert adapter._map_category("Attempted Information Leak") == ThreatCategory.CYBER
    assert adapter._map_category("A Network Trojan was detected") == ThreatCategory.CYBER
    assert adapter._map_category("Potential Recon Scan") == ThreatCategory.SURVEILLANCE


def test_parse_log_handles_malformed_json(tmp_path: Path):
    log_file = tmp_path / "eve.json"
    with log_file.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_sample_alert_event()) + "\n")
        handle.write("{not-json}\n")
        handle.write(json.dumps({"event_type": "flow"}) + "\n")
    adapter = SuricataAdapter()
    events = adapter.parse_eve_log(str(log_file))
    assert len(events) == 1


def test_parse_log_empty_file(tmp_path: Path):
    log_file = tmp_path / "empty_eve.json"
    log_file.write_text("", encoding="utf-8")
    adapter = SuricataAdapter()
    events = adapter.parse_eve_log(str(log_file))
    assert events == []
