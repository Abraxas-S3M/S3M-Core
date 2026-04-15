"""Unit tests for OTH-Gold maritime interoperability adapter.

Military/tactical context:
These tests preserve deterministic maritime track exchange behavior so coalition
naval COP feeds remain trustworthy in contested and disconnected environments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "services" / "interop" / "oth" / "oth_gold_adapter.py"


def _load_oth_gold_adapter() -> type:
    spec = importlib.util.spec_from_file_location("tests.oth_gold_adapter", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.OTHGoldAdapter


OTHGoldAdapter = _load_oth_gold_adapter()


def _text(node: ET.Element, path: str) -> str:
    child = node.find(path)
    assert child is not None and child.text is not None
    return child.text


def test_build_oth_gold_saudi_naval_track():
    adapter = OTHGoldAdapter()
    track = {
        "track_id": "RSNF-101",
        "affiliation": "friendly",
        "classification": "SECRET",
        "entity_type": "FRIENDLY_SHIP",
        "domain": "maritime",
        "position": {"lat": 26.2100, "lon": 50.6000},
        "course_deg": 92.5,
        "speed_mps": 12.0,
        "nationality": "SAU",
        "hull_number": "704",
        "timestamp": "2026-04-15T10:30:00Z",
        "source": "NAVAL_RADAR",
    }

    xml_payload = adapter.build_message([track])
    root = ET.fromstring(xml_payload)

    assert root.tag == "OTHGold"
    assert root.attrib.get("version") == "3.0"
    track_node = root.find("track")
    assert track_node is not None
    assert _text(track_node, "trackNumber") == "RSNF-101"
    assert _text(track_node, "identity") == "FRIEND"
    assert _text(track_node, "platform/nationality") == "SAU"
    assert _text(track_node, "platform/hullNumber") == "704"


def test_parse_oth_gold_roundtrip():
    adapter = OTHGoldAdapter()
    original = {
        "track_id": "GULF-TRACK-77",
        "affiliation": "neutral",
        "classification": "CONFIDENTIAL",
        "entity_type": "CIVILIAN",
        "domain": "maritime",
        "position": {"lat": 25.2711, "lon": 55.3075},
        "course_deg": 41.0,
        "speed_mps": 8.7,
        "nationality": "SAU",
        "hull_number": "MT-909",
        "timestamp": "2026-04-15T12:00:00Z",
        "source": "AIS",
    }

    xml_payload = adapter.build_message([original])
    parsed = adapter.parse_message(xml_payload)

    assert len(parsed) == 1
    restored = parsed[0]
    assert restored["position"]["lat"] == pytest.approx(original["position"]["lat"], abs=1e-6)
    assert restored["position"]["lon"] == pytest.approx(original["position"]["lon"], abs=1e-6)
    assert restored["course_deg"] == pytest.approx(original["course_deg"], abs=1e-3)
    assert restored["speed_mps"] == pytest.approx(original["speed_mps"], abs=1e-3)


def test_speed_knots_conversion():
    adapter = OTHGoldAdapter()
    track = {
        "track_id": "SPD-1",
        "affiliation": "friendly",
        "entity_type": "FRIENDLY_SHIP",
        "domain": "maritime",
        "position": {"lat": 24.0, "lon": 54.0},
        "course_deg": 180.0,
        "speed_mps": 10.0,
        "nationality": "SAU",
    }

    xml_payload = adapter.build_message([track])
    root = ET.fromstring(xml_payload)
    speed_knots = float(_text(root.find("track"), "kinematics/speed"))  # type: ignore[arg-type]
    assert speed_knots == pytest.approx(19.438, abs=1e-3)

    parsed = adapter.parse_message(xml_payload)
    assert parsed[0]["speed_mps"] == pytest.approx(10.0, abs=1e-3)


def test_identity_mapping_all_affiliations():
    adapter = OTHGoldAdapter()
    assert adapter._identity_map("friendly") == "FRIEND"
    assert adapter._identity_map("hostile") == "HOSTILE"
    assert adapter._identity_map("neutral") == "NEUTRAL"
    assert adapter._identity_map("unknown") == "UNKNOWN"


def test_maritime_tracks_only():
    adapter = OTHGoldAdapter()
    tracks = [
        {
            "track_id": "SEA-01",
            "affiliation": "friendly",
            "entity_type": "FRIENDLY_SHIP",
            "domain": "maritime",
            "position": {"lat": 26.0, "lon": 50.0},
            "speed_mps": 7.5,
            "course_deg": 15.0,
            "nationality": "SAU",
        },
        {
            "track_id": "AIR-01",
            "affiliation": "friendly",
            "entity_type": "FRIENDLY_UAV",
            "domain": "air",
            "position": {"lat": 26.1, "lon": 50.1},
            "speed_mps": 55.0,
            "course_deg": 20.0,
            "nationality": "SAU",
        },
    ]

    xml_payload = adapter.build_message(tracks)
    root = ET.fromstring(xml_payload)
    track_nodes = root.findall("track")
    assert len(track_nodes) == 1
    assert _text(track_nodes[0], "trackNumber") == "SEA-01"
