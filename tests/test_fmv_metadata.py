"""Tests for STANAG 4609 FMV metadata encoding and API routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.interop.fmv import FMVMetadataBuilder, KLVEncoder
from src.api import fmv_routes


def _sample_uav_status() -> dict:
    return {
        "platform_heading": 87.25,
        "platform_pitch": -2.5,
        "platform_roll": 1.25,
        "position": {
            "latitude": 24.7136,
            "longitude": 46.6753,
            "altitude": 1412.8,
        },
    }


def _sample_payload_status() -> dict:
    return {
        "sensor_position": {
            "latitude": 24.7136,
            "longitude": 46.6754,
            "altitude": 1415.2,
        },
        "fov": {"horizontal": 22.0, "vertical": 12.0},
        "target_location": {"latitude": 24.7125, "longitude": 46.6799},
        "uas_local_set_version": 13,
    }


def _test_client(monkeypatch, tmp_path: Path) -> tuple[TestClient, FMVMetadataBuilder]:
    builder = FMVMetadataBuilder(
        config={
            "klv_standard": "MISB_0601",
            "embed_in_stream": False,
            "register_in_nsili": True,
        },
        nsili_catalog_path=tmp_path / "nsili_fmv_catalog.json",
    )
    monkeypatch.setattr(fmv_routes, "_builder", builder)
    monkeypatch.setattr(fmv_routes, "_fmv_config", builder.config)
    app = FastAPI()
    app.include_router(fmv_routes.fmv_router)
    return TestClient(app), builder


def test_klv_encoder_roundtrip_with_long_ber_length():
    encoder = KLVEncoder()
    value = bytes([7]) * 130
    encoded = encoder.encode_klv(22, value)
    decoded = encoder.decode_klv(encoded)
    assert decoded == [(22, value)]


def test_metadata_build_and_parse_roundtrip():
    builder = FMVMetadataBuilder()
    packet = builder.build_metadata_packet(
        uav_status=_sample_uav_status(),
        payload_status=_sample_payload_status(),
        timestamp=1_713_264_321.125,
    )
    parsed = builder.parse_metadata_packet(packet)
    assert parsed["timestamp"] == 1_713_264_321.125
    assert parsed["platform_position"]["heading_deg"] == 87.25
    assert parsed["sensor_position"]["latitude"] == 24.7136
    assert parsed["fov"]["horizontal_deg"] == 22.0
    assert parsed["target_location"] == {"latitude": 24.7125, "longitude": 46.6799}
    assert parsed["uas_local_set_version"] == 13


def test_parse_metadata_rejects_truncated_payload():
    builder = FMVMetadataBuilder()
    packet = builder.build_metadata_packet(
        uav_status=_sample_uav_status(),
        payload_status=_sample_payload_status(),
        timestamp=1_713_264_321.125,
    )
    truncated = packet[:-3]
    try:
        builder.parse_metadata_packet(truncated)
        assert False, "expected ValueError for truncated packet"
    except ValueError:
        assert True


def test_register_with_nsili_writes_video_product(tmp_path: Path):
    catalog = tmp_path / "catalog.json"
    builder = FMVMetadataBuilder(nsili_catalog_path=catalog)
    metadata = {"timestamp": 1_713_264_321.125, "fov": {"horizontal_deg": 18.0, "vertical_deg": 9.0}}
    product_id = builder.register_with_nsili(metadata=metadata, video_reference="droneops://missions/m1/feed-1")
    assert product_id.startswith("fmv-")
    rows = json.loads(catalog.read_text(encoding="utf-8"))
    assert rows[-1]["productId"] == product_id
    assert rows[-1]["productType"] == "VIDEO"
    assert rows[-1]["videoReference"] == "droneops://missions/m1/feed-1"


def test_fmv_routes_build_parse_and_register(monkeypatch, tmp_path: Path):
    client, builder = _test_client(monkeypatch, tmp_path)
    build_resp = client.post(
        "/interop/fmv/metadata/build",
        json={
            "uav_status": _sample_uav_status(),
            "payload_status": _sample_payload_status(),
            "timestamp": 1_713_264_321.125,
        },
    )
    assert build_resp.status_code == 200
    packet_hex = build_resp.json()["metadata_packet_hex"]

    parse_resp = client.post("/interop/fmv/metadata/parse", json={"metadata_packet_hex": packet_hex})
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    assert parsed["platform_position"]["roll_deg"] == 1.25
    assert parsed["target_location"]["longitude"] == 46.6799

    register_resp = client.post(
        "/interop/fmv/register",
        json={
            "metadata": parsed,
            "video_reference": "droneops://missions/m1/feed-1",
        },
    )
    assert register_resp.status_code == 200
    assert register_resp.json()["product_type"] == "VIDEO"

    rows = json.loads(builder.nsili_catalog_path.read_text(encoding="utf-8"))
    assert rows[-1]["productType"] == "VIDEO"


def test_fmv_routes_reject_invalid_packet(monkeypatch, tmp_path: Path):
    client, _ = _test_client(monkeypatch, tmp_path)
    resp = client.post("/interop/fmv/metadata/parse", json={"metadata_packet_hex": "0102zz"})
    assert resp.status_code == 400


def test_fmv_routes_status(monkeypatch, tmp_path: Path):
    client, _ = _test_client(monkeypatch, tmp_path)
    resp = client.get("/interop/fmv/status")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["standard"] == "MISB_0601"
    assert payload["embed_in_stream"] is False
    assert payload["register_in_nsili"] is True
