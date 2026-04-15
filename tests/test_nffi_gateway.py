"""Unit tests for NFFI message and gateway behavior."""

from __future__ import annotations

import json
import math
import re

from services.interop.nffi import NFFIGateway, NFFIMessageBuilder
from services.interop.registry import InteropRegistry


def _distance_meters(pos_a: list[float], pos_b: list[float]) -> float:
    lat1, lon1, alt1 = pos_a
    lat2, lon2, alt2 = pos_b
    r = 6378137.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1e-15, 1.0 - a)))
    horizontal = r * c
    return math.sqrt(horizontal * horizontal + (alt2 - alt1) ** 2)


def test_build_nffi_message_saudi_tracks():
    builder = NFFIMessageBuilder()
    xml = builder.build_message(
        tracks=[
            {
                "unit_id": "falcon-11",
                "position": [24.7136, 46.6753, 620.0],
                "role": "friendly_armor",
                "status": "active",
                "updated_at": "2026-04-15T12:30:45+00:00",
            }
        ],
        country_iso3="SAU",
        system_id="S3M-FALCON",
    )
    assert "<nffi" in xml
    assert "urn:nffi:xml:1.4" in xml
    assert "<trackSource>SAU</trackSource>" in xml
    assert "<systemId>S3M-FALCON</systemId>" in xml
    assert "<deviceId>falcon-11</deviceId>" in xml


def test_parse_nffi_message_roundtrip():
    builder = NFFIMessageBuilder()
    tracks = [
        {
            "unit_id": "falcon-12",
            "position": [24.7000000, 46.6000000, 600.5],
            "role": "friendly_uav",
            "status": "active",
            "updated_at": "2026-04-15T10:00:00+00:00",
        },
        {
            "unit_id": "falcon-13",
            "position": [24.7100000, 46.6100000, 601.5],
            "role": "friendly_armor",
            "status": "damaged",
            "updated_at": "2026-04-15T10:00:05+00:00",
        },
    ]
    xml = builder.build_message(tracks=tracks, country_iso3="SAU", system_id="S3M-FALCON")
    parsed = builder.parse_message(xml)
    assert len(parsed) == 2
    for idx, item in enumerate(parsed):
        assert item["unit_id"] == tracks[idx]["unit_id"]
        assert _distance_meters(item["position"], tracks[idx]["position"]) <= 1.0


def test_nffi_filters_hostile_tracks():
    builder = NFFIMessageBuilder()
    xml = builder.build_message(
        tracks=[
            {
                "unit_id": "blue-1",
                "position": [24.7, 46.6, 600.0],
                "role": "friendly_uav",
                "status": "active",
            },
            {
                "unit_id": "red-9",
                "position": [24.8, 46.7, 500.0],
                "role": "enemy_uav",
                "status": "active",
                "classification": "hostile",
            },
        ],
        country_iso3="SAU",
        system_id="S3M-FALCON",
    )
    assert "blue-1" in xml
    assert "red-9" not in xml
    parsed = builder.parse_message(xml)
    assert len(parsed) == 1
    assert parsed[0]["unit_id"] == "blue-1"


def test_nffi_datetime_format_14digit():
    builder = NFFIMessageBuilder()
    xml = builder.build_message(
        tracks=[
            {
                "unit_id": "falcon-14",
                "position": [24.7, 46.6, 600.0],
                "role": "friendly",
                "status": "active",
                "updated_at": "2026-04-15T13:14:15+00:00",
            }
        ],
        country_iso3="SAU",
        system_id="S3M-FALCON",
    )
    match = re.search(r"<dateTime>(.*?)</dateTime>", xml)
    assert match is not None
    date_time_value = match.group(1)
    assert re.fullmatch(r"\d{14}", date_time_value) is not None
    assert "T" not in date_time_value


def test_iso3_codes_all_gcc_partners():
    registry = InteropRegistry()
    iso3 = registry.get_iso3_codes()
    expected = {
        178: "SAU",
        223: "ARE",
        117: "KWT",
        16: "BHR",
        164: "QAT",
        154: "OMN",
    }
    for code, alpha3 in expected.items():
        assert iso3[code] == alpha3


def test_iso3_codes_all_nato_partners():
    registry = InteropRegistry()
    iso3 = registry.get_iso3_codes()
    expected = {
        225: "USA",
        224: "GBR",
        71: "FRA",
        78: "DEU",
        105: "ITA",
        198: "ESP",
        222: "TUR",
        39: "CAN",
        145: "NLD",
        146: "NOR",
    }
    for code, alpha3 in expected.items():
        assert iso3[code] == alpha3


def test_nffi_status_mapping():
    builder = NFFIMessageBuilder()
    assert builder._status_to_nffi("active") == "OPERATIONAL"
    assert builder._status_to_nffi("damaged") == "DEGRADED"
    assert builder._status_to_nffi("destroyed") == "DESTROYED"
    assert builder._nffi_to_status("OPERATIONAL") == "active"
    assert builder._nffi_to_status("DEGRADED") == "damaged"
    assert builder._nffi_to_status("DESTROYED") == "destroyed"


def test_nffi_offline_fallback(tmp_path):
    outbox_dir = tmp_path / "nffi_outbox"
    gateway = NFFIGateway(
        config={
            "transport_profile": "IP-1",
            "gateway_url": None,
            "track_source_country": "SAU",
            "system_id": "S3M-FALCON",
            "outbox_dir": str(outbox_dir),
        },
        message_builder=NFFIMessageBuilder(),
    )
    published = gateway.publish_friendly_tracks(
        [
            {
                "unit_id": "blue-2",
                "position": [24.7, 46.6, 600.0],
                "role": "friendly_armor",
                "status": "active",
            }
        ]
    )
    assert published == 1
    files = list(outbox_dir.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["message_type"] == "NFFI_TRACK"
    assert "<deviceId>blue-2</deviceId>" in payload["xml"]
