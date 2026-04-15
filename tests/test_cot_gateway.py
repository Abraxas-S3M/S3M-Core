"""Tests for S3M CoT/TAK interoperability gateway."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from services.interop.cot import CotBridge, CotEventFactory, CotTransport
from src.security.interop.dis_adapter import DIS_ENTITY_MAP


def _sample_track() -> dict:
    return {
        "unit_id": "uav-1",
        "entity_type": "FRIENDLY_UAV",
        "affiliation": "friendly",
        "domain": "air",
        "position": [24.7136, 46.6753, 650.0],
        "heading": 42.5,
        "speed": 55.0,
        "callsign": "S3M-UAV1",
        "time": "2026-04-15T12:00:00Z",
    }


def test_build_cot_event_friendly_uav():
    factory = CotEventFactory({"cot": {"stale_seconds": 120}})
    xml = factory.build_event(_sample_track())
    root = ET.fromstring(xml)
    assert root.tag == "event"
    assert root.attrib["type"] == "a-f-A"
    point = root.find("point")
    assert point is not None
    assert float(point.attrib["lat"]) == 24.7136
    assert float(point.attrib["lon"]) == 46.6753


def test_parse_cot_event_roundtrip():
    factory = CotEventFactory({"cot": {"stale_seconds": 120}})
    source = _sample_track()
    xml = factory.build_event(source)
    parsed = factory.parse_event(xml)
    assert parsed["uid"] == source["unit_id"]
    assert parsed["type"] == "a-f-A"
    assert parsed["callsign"] == source["callsign"]
    assert abs(parsed["lat"] - source["position"][0]) < 1e-6
    assert abs(parsed["lon"] - source["position"][1]) < 1e-6
    assert abs(parsed["hae"] - source["position"][2]) < 1e-6
    assert abs(parsed["course"] - source["heading"]) < 1e-6
    assert abs(parsed["speed"] - source["speed"]) < 1e-6
    assert parsed["affiliation"] == source["affiliation"]
    assert parsed["time"] == source["time"]


def test_s3m_to_cot_type_mapping_all_entities():
    factory = CotEventFactory()
    for key, payload in DIS_ENTITY_MAP.items():
        upper = key.upper()
        if upper.startswith("FRIENDLY_"):
            affiliation = "friendly"
        elif upper.startswith("ENEMY_"):
            affiliation = "hostile"
        elif upper.startswith("UNKNOWN"):
            affiliation = "unknown"
        else:
            affiliation = "neutral"
        domain = {2: "air", 3: "surface"}.get(int(payload.get("domain", 1)), "ground")
        cot_type = factory._s3m_type_to_cot(entity_type=key, affiliation=affiliation, domain=domain)
        assert cot_type in {"a-f-A", "a-f-G", "a-f-S", "a-h-A", "a-h-G", "a-h-S", "a-n-G", "a-u-G"}


def test_cot_to_s3m_type_mapping_reverse():
    factory = CotEventFactory()
    for cot_type, expected_affiliation in (
        ("a-f-G", "friendly"),
        ("a-h-G", "hostile"),
        ("a-n-G", "neutral"),
        ("a-u-G", "unknown"),
    ):
        _entity_type, affiliation, _domain = factory._cot_to_s3m_type(cot_type)
        assert affiliation == expected_affiliation


def test_cot_bridge_publish_tracks_returns_count():
    class _MockTransport:
        def __init__(self):
            self.sent = []

        def send(self, xml: str) -> bool:
            self.sent.append(xml)
            return True

        def receive(self):
            return None

    transport = _MockTransport()
    bridge = CotBridge(transport=transport, event_factory=CotEventFactory())
    count = bridge.publish_tracks([_sample_track(), _sample_track()])
    assert count == 2
    assert len(transport.sent) == 2


def test_cot_bridge_ingest_received_returns_s3m_format():
    factory = CotEventFactory()
    xml = factory.build_event(_sample_track())

    class _MockTransport:
        def __init__(self, payload):
            self.payload = payload
            self.calls = 0

        def send(self, _xml: str) -> bool:
            return True

        def receive(self):
            if self.calls == 0:
                self.calls += 1
                return self.payload
            return None

    bridge = CotBridge(transport=_MockTransport(xml), event_factory=factory)
    rows = bridge.ingest_received()
    assert len(rows) == 1
    assert rows[0]["unit_id"] == "uav-1"
    assert rows[0]["status"] == "active"
    assert rows[0]["role"] == "friendly_air"
    assert isinstance(rows[0]["position"], list) and len(rows[0]["position"]) == 3


def test_cot_transport_offline_fallback_writes_outbox(tmp_path: Path):
    transport = CotTransport({"cot": {"outbox_dir": str(tmp_path)}})
    xml = "<event version='2.0' uid='1' type='a-f-G'></event>"
    sent = transport.send(xml)
    assert sent is False
    outbox_files = list(tmp_path.glob("*.xml"))
    assert len(outbox_files) == 1
    assert outbox_files[0].read_text(encoding="utf-8") == xml


def test_cot_event_stale_calculation():
    factory = CotEventFactory({"cot": {"stale_seconds": 180}})
    xml = factory.build_event(_sample_track())
    root = ET.fromstring(xml)
    time_value = datetime.fromisoformat(root.attrib["time"].replace("Z", "+00:00"))
    stale_value = datetime.fromisoformat(root.attrib["stale"].replace("Z", "+00:00"))
    assert int((stale_value - time_value).total_seconds()) == 180


def test_cot_coordinates_use_hae_not_msl():
    factory = CotEventFactory()
    track = _sample_track()
    track.pop("position")
    track["lat"] = 24.7136
    track["lon"] = 46.6753
    track["hae"] = 777.0
    track["msl"] = 555.0
    xml = factory.build_event(track)
    root = ET.fromstring(xml)
    point = root.find("point")
    assert point is not None
    assert float(point.attrib["hae"]) == 777.0
    assert float(point.attrib["hae"]) != float(track["msl"])
    assert root.attrib["time"].endswith("Z")
    assert datetime.fromisoformat(root.attrib["time"].replace("Z", "+00:00")).tzinfo == timezone.utc

