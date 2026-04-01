#!/usr/bin/env python3
"""API tests for Layer 09 sensor analytics endpoints."""

from __future__ import annotations

import os
from pathlib import Path
import sys

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.server import app  # noqa: E402


def _make_csv(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "MMSI,timestamp,lat,lon,speed,course,heading,vessel_name,vessel_type,destination,nav_status",
                "403999001,2026-04-01T10:00:00Z,26.0,50.0,12.5,90.0,92.0,TEST-1,70,DMMB,0",
                "403999002,2026-04-01T10:05:00Z,26.2,50.2,10.0,120.0,122.0,TEST-2,30,DMMB,0",
            ]
        ),
        encoding="utf-8",
    )


def _make_image(path: Path) -> None:
    from PIL import Image  # type: ignore

    arr = np.zeros((256, 256), dtype=np.uint8)
    arr[80:95, 100:130] = 245
    Image.fromarray(arr).save(path)


def test_sensor_analytics_endpoints(tmp_path: Path) -> None:
    client = TestClient(app)
    csv_path = tmp_path / "ais.csv"
    image_path = tmp_path / "sar.png"
    export_path = tmp_path / "picture.geojson"
    _make_csv(csv_path)
    _make_image(image_path)

    assert client.post("/sensor-analytics/sar/detect", json={"image_path": str(image_path)}).status_code == 200
    assert client.get("/sensor-analytics/sar/model").status_code == 200
    assert client.post("/sensor-analytics/ais/ingest", json={"filepath": str(csv_path)}).status_code == 200
    assert client.get("/sensor-analytics/ais/vessels").status_code == 200
    assert client.get("/sensor-analytics/ais/dark").status_code == 200
    assert client.post("/sensor-analytics/border/scan").status_code == 200

    zones_resp = client.get("/sensor-analytics/border/zones")
    assert zones_resp.status_code == 200
    assert len(zones_resp.json()) == 6

    assert client.get("/sensor-analytics/maritime/picture").status_code == 200
    assert client.get("/sensor-analytics/maritime/stats").status_code == 200

    export_resp = client.post(
        "/sensor-analytics/maritime/export",
        json={"filepath": str(export_path), "format": "geojson"},
    )
    assert export_resp.status_code == 200
    assert export_path.exists()

    assert client.get("/sensor-analytics/status").status_code == 200
    datasets = client.get("/sensor-analytics/datasets")
    assert datasets.status_code == 200
    assert "datasets" in datasets.json()
