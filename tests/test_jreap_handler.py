"""Unit tests for JREAP-C header and J-series decode paths."""

from __future__ import annotations

import struct
from unittest.mock import MagicMock

from services.interop.jreap import JREAPBridge, JREAPHandler


def _encode_lat_23bit(lat_deg: float) -> int:
    scaled = int(round(((float(lat_deg) + 90.0) / 180.0) * (1 << 23)))
    return max(0, min((1 << 23) - 1, scaled))


def _encode_lon_24bit(lon_deg: float) -> int:
    scaled = int(round(((float(lon_deg) + 180.0) / 360.0) * (1 << 24)))
    return max(0, min((1 << 24) - 1, scaled))


def _build_j2_2_record(
    track_number: int,
    lat_deg: float,
    lon_deg: float,
    altitude_m: int = 1500,
    speed: int = 420,
    heading_deg: float = 95.0,
    iff: int = 1,
    identity: int = 2,
) -> bytes:
    heading_raw = int(round((float(heading_deg) / 360.0) * (1 << 9))) & 0x1FF
    word = 0
    word |= (int(track_number) & 0x1FFF) << 91
    word |= (_encode_lat_23bit(lat_deg) & ((1 << 23) - 1)) << 68
    word |= (_encode_lon_24bit(lon_deg) & ((1 << 24) - 1)) << 44
    word |= (int(altitude_m) & 0xFFFF) << 28
    word |= (int(speed) & 0x03FF) << 18
    word |= (heading_raw & 0x01FF) << 9
    word |= (int(iff) & 0x07) << 6
    word |= (int(identity) & 0x03) << 4
    return word.to_bytes(13, byteorder="big", signed=False)


def test_parse_jreap_header_20bytes():
    handler = JREAPHandler()
    header = struct.pack("!HHIQI", 1, 1, 42, 1_710_000_000_000_000, 13)
    parsed = handler.parse_jreap_header(header)
    assert parsed["protocol_version"] == 1
    assert parsed["message_type"] == 1
    assert parsed["sequence_number"] == 42
    assert parsed["timestamp_us"] == 1_710_000_000_000_000
    assert parsed["payload_length"] == 13


def test_parse_j2_2_air_track_position():
    handler = JREAPHandler()
    payload = _build_j2_2_record(track_number=301, lat_deg=24.7136, lon_deg=46.6753)
    rows = handler.parse_j_series(payload, "J2.2")
    assert len(rows) == 1
    row = rows[0]
    assert row["domain"] == "air"
    assert abs(float(row["latitude"]) - 24.7136) < 0.01
    assert abs(float(row["longitude"]) - 46.6753) < 0.01


def test_encode_decode_header_roundtrip():
    handler = JREAPHandler({"protocol_version": 1, "initial_sequence": 77})
    payload = b"\x01\x02\x03\x04"
    header = handler.encode_jreap_header(1, payload)
    parsed = handler.parse_jreap_header(header)
    assert parsed["protocol_version"] == 1
    assert parsed["message_type"] == 1
    assert parsed["sequence_number"] == 78
    assert parsed["payload_length"] == len(payload)
    assert parsed["timestamp_us"] > 0


def test_lat_23bit_decode_riyadh():
    handler = JREAPHandler()
    raw = _encode_lat_23bit(24.7136)
    decoded = handler._decode_lat_23bit(raw)
    assert abs(decoded - 24.7136) < 0.01


def test_lon_24bit_decode_riyadh():
    handler = JREAPHandler()
    raw = _encode_lon_24bit(46.6753)
    decoded = handler._decode_lon_24bit(raw)
    assert abs(decoded - 46.6753) < 0.01


def test_jreap_bridge_crossfeed_to_cot():
    bridge = JREAPBridge({"jreap": {"listen_port": 5555, "supported_j_series": ["J2.2"]}})
    record = _build_j2_2_record(track_number=909, lat_deg=24.7136, lon_deg=46.6753)
    # Tactical framing note: mixed payload includes message code + record length.
    payload = struct.pack("!BB", 0x22, len(record)) + record
    packet = bridge.handler.encode_jreap_header(1, payload) + payload
    with bridge._lock:
        bridge._received_packets.append(packet)

    cot_bridge = MagicMock()
    cot_bridge.publish_event.return_value = True

    forwarded = bridge.crossfeed_to_cot(cot_bridge)
    assert forwarded == 1
    assert cot_bridge.publish_event.call_count == 1
    event = cot_bridge.publish_event.call_args[0][0]
    assert event["uid"] == "J22-909"
    assert abs(float(event["lat"]) - 24.7136) < 0.01
    assert abs(float(event["lon"]) - 46.6753) < 0.01
