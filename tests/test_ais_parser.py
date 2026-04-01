#!/usr/bin/env python3
"""Unit tests for AIS parser."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import tempfile

from services.sensor_analytics.ais.parser import AISParser


def _build_type1_sentence(
    mmsi: int = 123456789,
    lat_deg: float = 25.0,
    lon_deg: float = 50.0,
    sog_knots: float = 12.3,
    cog_deg: float = 180.0,
    heading_deg: int = 179,
    nav_status: int = 0,
) -> str:
    bits = [0] * 168

    def set_bits(start: int, length: int, value: int) -> None:
        for i in range(length):
            shift = length - 1 - i
            bits[start + i] = (value >> shift) & 1

    set_bits(0, 6, 1)
    set_bits(8, 30, mmsi)
    set_bits(38, 4, nav_status)
    set_bits(50, 10, int(round(sog_knots * 10)))

    lon_raw = int(round(lon_deg * 600000))
    lat_raw = int(round(lat_deg * 600000))
    if lon_raw < 0:
        lon_raw = (1 << 28) + lon_raw
    if lat_raw < 0:
        lat_raw = (1 << 27) + lat_raw
    set_bits(61, 28, lon_raw)
    set_bits(89, 27, lat_raw)
    set_bits(116, 12, int(round(cog_deg * 10)))
    set_bits(128, 9, heading_deg)

    payload_chars = []
    for i in range(0, len(bits), 6):
        chunk = bits[i : i + 6]
        val = 0
        for bit in chunk:
            val = (val << 1) | bit
        char_code = val + 48
        if char_code > 87:
            char_code += 8
        payload_chars.append(chr(char_code))
    payload = "".join(payload_chars)
    return f"!AIVDM,1,1,,A,{payload},0*00"


def test_decode_payload_converts_6bit_ascii() -> None:
    parser = AISParser()
    bits = parser.decode_payload("1")
    assert len(bits) == 6
    assert bits == [0, 0, 0, 0, 0, 1]


def test_parse_nmea_valid_aivdm_sentence() -> None:
    parser = AISParser()
    sentence = _build_type1_sentence()
    msg = parser.parse_nmea(sentence)
    assert msg is not None
    assert msg.message_type == 1
    assert msg.mmsi == "123456789"
    assert abs(msg.lat - 25.0) < 0.01
    assert abs(msg.lon - 50.0) < 0.01


def test_parse_csv_sample_data() -> None:
    parser = AISParser()
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        handle.write(
            "MMSI,timestamp,lat,lon,speed,course,heading,vessel_name,vessel_type,destination,nav_status\n"
            "123456789,2026-01-01T00:00:00Z,25.0,50.0,12.0,180.0,180.0,TestVessel,70,JUBAIL,0\n"
        )
        path = handle.name
    try:
        msgs = parser.parse_csv(path)
        assert len(msgs) == 1
        assert msgs[0].mmsi == "123456789"
        assert msgs[0].vessel_name == "TestVessel"
    finally:
        os.unlink(path)


def test_parse_file_auto_detect_csv() -> None:
    parser = AISParser()
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
        handle.write(
            "MMSI,timestamp,lat,lon,speed,course,heading,vessel_name,vessel_type,destination,nav_status\n"
            "987654321,2026-01-01T01:00:00Z,26.0,49.5,10.0,120.0,120.0,VesselB,80,DAMMAM,0\n"
        )
        path = handle.name
    try:
        msgs = parser.parse_file(path)
        assert len(msgs) == 1
        assert msgs[0].mmsi == "987654321"
    finally:
        os.unlink(path)
