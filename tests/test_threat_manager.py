"""Tests for S3M Phase 5 threat manager."""

import json
from pathlib import Path

from src.threat_detection.models import ThreatCategory, ThreatLevel, ThreatSource
from src.threat_detection.threat_manager import ThreatManager


def test_ingest_manual():
    manager = ThreatManager(max_entries=10)
    event = manager.ingest_manual(
        title="Manual contact report",
        description="Operator reports suspicious signal activity",
        level="HIGH",
        category="ELECTRONIC_WARFARE",
    )
    assert event.source == ThreatSource.MANUAL
    assert event.level == ThreatLevel.HIGH


def test_get_threats_with_filters():
    manager = ThreatManager(max_entries=20)
    manager.ingest_manual("Cyber alert", "desc", "MEDIUM", "CYBER")
    manager.ingest_manual("Kinetic alert", "desc", "HIGH", "KINETIC")
    filtered = manager.get_threats(category="KINETIC", limit=10)
    assert len(filtered) == 1
    assert filtered[0].category == ThreatCategory.KINETIC


def test_get_stats():
    manager = ThreatManager(max_entries=10)
    manager.ingest_manual("One", "desc", "LOW", "CYBER")
    stats = manager.get_stats()
    assert stats["total_events"] == 1
    assert "LOW" in stats["events_by_level"]


def test_log_rotation():
    manager = ThreatManager(max_entries=3)
    manager.ingest_manual("1", "desc", "LOW", "CYBER")
    manager.ingest_manual("2", "desc", "LOW", "CYBER")
    manager.ingest_manual("3", "desc", "LOW", "CYBER")
    manager.ingest_manual("4", "desc", "LOW", "CYBER")
    assert len(manager.get_threats(limit=10)) == 3


def test_export_log(tmp_path: Path):
    manager = ThreatManager(max_entries=10)
    manager.ingest_manual("Export test", "desc", "INFO", "UNKNOWN")
    output_file = tmp_path / "threat_export.json"
    manager.export_log(str(output_file))
    assert output_file.exists()
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["total_events"] == 1
