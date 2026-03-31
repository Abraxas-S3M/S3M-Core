"""Tests for WazuhAdapter in S3M Layer 02."""

import json

from src.threat_detection.models import ThreatCategory, ThreatLevel
from src.threat_detection.wazuh_adapter import WazuhAdapter


def test_parse_wazuh_alert():
    adapter = WazuhAdapter()
    alert = {
        "timestamp": "2026-03-31T10:35:00+00:00",
        "agent": {"name": "alpha-endpoint"},
        "rule": {
            "id": "5710",
            "level": 12,
            "description": "Multiple authentication failures detected",
            "groups": ["authentication_failure", "intrusion_detection"],
        },
        "srcip": "10.0.0.5",
        "full_log": "Failed password for invalid user root",
    }
    event = adapter.parse_alert(alert)
    assert event is not None
    assert event.level == ThreatLevel.HIGH
    assert event.category == ThreatCategory.CYBER
    assert event.raw_data["agent_name"] == "alpha-endpoint"


def test_level_mapping():
    adapter = WazuhAdapter()
    assert adapter._map_rule_level(2) == ThreatLevel.INFO
    assert adapter._map_rule_level(6) == ThreatLevel.LOW
    assert adapter._map_rule_level(9) == ThreatLevel.MEDIUM
    assert adapter._map_rule_level(13) == ThreatLevel.HIGH
    assert adapter._map_rule_level(15) == ThreatLevel.CRITICAL


def test_group_mapping():
    adapter = WazuhAdapter()
    assert adapter._map_groups(["intrusion_detection"]) == ThreatCategory.CYBER
    assert adapter._map_groups(["scan"]) == ThreatCategory.SURVEILLANCE


def test_malformed_json(tmp_path):
    path = tmp_path / "alerts.json"
    path.write_text("{bad}\n", encoding="utf-8")
    adapter = WazuhAdapter()
    events = adapter.parse_alerts_file(str(path))
    assert events == []
