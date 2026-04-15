"""Tests for OGC WMS/WFS clients, GeoJSON adapter, and API routes."""

from __future__ import annotations

from typing import Any
from urllib import error, parse

from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.interop.ogc.wfs_client as wfs_module
import services.interop.ogc.wms_client as wms_module
from services.interop.ogc import GeoJSONAdapter, WFSClient, WMSClient
from src.api.ogc_routes import _OGC_CONFIG, ogc_router


class _MockHTTPResponse:
    def __init__(self, payload: bytes, content_type: str = "application/xml", status: int = 200) -> None:
        self.status = status
        self._payload = payload
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_MockHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb


def test_wms_get_capabilities_parses_layers(monkeypatch) -> None:
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Service>
    <Title>S3M Coalition WMS</Title>
    <Abstract>Raster map exchange</Abstract>
  </Service>
  <Capability>
    <Layer>
      <Title>Root</Title>
      <Layer>
        <Name>cop_base</Name>
        <Title>Coalition COP Base</Title>
        <Abstract>Common operating picture map</Abstract>
        <CRS>EPSG:4326</CRS>
        <EX_GeographicBoundingBox>
          <westBoundLongitude>46.0</westBoundLongitude>
          <eastBoundLongitude>48.0</eastBoundLongitude>
          <southBoundLatitude>24.0</southBoundLatitude>
          <northBoundLatitude>26.0</northBoundLatitude>
        </EX_GeographicBoundingBox>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

    def fake_urlopen(req, timeout=8.0):  # noqa: ARG001
        _ = req
        return _MockHTTPResponse(xml)

    monkeypatch.setattr(wms_module.request, "urlopen", fake_urlopen)

    client = WMSClient("http://maps.example/wms")
    capabilities = client.get_capabilities()

    assert capabilities["online"] is True
    assert capabilities["service"] == "WMS"
    assert capabilities["version"] == "1.3.0"
    assert capabilities["title"] == "S3M Coalition WMS"
    assert len(capabilities["layers"]) == 1
    assert capabilities["layers"][0]["name"] == "cop_base"
    assert capabilities["layers"][0]["bbox"] == (46.0, 24.0, 48.0, 26.0)


def test_wms_get_map_builds_expected_query(monkeypatch) -> None:
    captured_url: dict[str, str] = {}

    def fake_urlopen(req, timeout=8.0):  # noqa: ARG001
        captured_url["url"] = req.full_url
        return _MockHTTPResponse(b"\x89PNG\r\n", content_type="image/png")

    monkeypatch.setattr(wms_module.request, "urlopen", fake_urlopen)

    client = WMSClient("http://maps.example/wms")
    payload = client.get_map(
        layers=["cop_base", "terrain"],
        bbox=(46.0, 24.0, 48.0, 26.0),
        width=512,
        height=512,
    )
    parsed = parse.urlparse(captured_url["url"])
    params = parse.parse_qs(parsed.query)

    assert payload.startswith(b"\x89PNG")
    assert params["SERVICE"] == ["WMS"]
    assert params["REQUEST"] == ["GetMap"]
    assert params["LAYERS"] == ["cop_base,terrain"]
    assert params["WIDTH"] == ["512"]
    assert params["HEIGHT"] == ["512"]


def test_wms_get_map_graceful_failure_returns_empty(monkeypatch) -> None:
    def failing_urlopen(req, timeout=8.0):  # noqa: ARG001
        _ = req
        raise error.URLError("offline")

    monkeypatch.setattr(wms_module.request, "urlopen", failing_urlopen)
    client = WMSClient("http://maps.example/wms")
    payload = client.get_map(
        layers=["cop_base"],
        bbox=(46.0, 24.0, 48.0, 26.0),
        width=256,
        height=256,
    )
    assert payload == b""


def test_wfs_capabilities_and_feature_types(monkeypatch) -> None:
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<wfs:WFS_Capabilities version="2.0.0"
    xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:ows="http://www.opengis.net/ows/1.1">
  <ows:ServiceIdentification>
    <ows:Title>S3M Coalition WFS</ows:Title>
    <ows:Abstract>Vector feature exchange</ows:Abstract>
  </ows:ServiceIdentification>
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>s3m:tracks</wfs:Name>
      <wfs:Title>Tracks</wfs:Title>
      <wfs:DefaultCRS>EPSG:4326</wfs:DefaultCRS>
      <ows:WGS84BoundingBox>
        <ows:LowerCorner>46.0 24.0</ows:LowerCorner>
        <ows:UpperCorner>48.0 26.0</ows:UpperCorner>
      </ows:WGS84BoundingBox>
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>
"""

    def fake_urlopen(req, timeout=8.0):  # noqa: ARG001
        _ = req
        return _MockHTTPResponse(xml)

    monkeypatch.setattr(wfs_module.request, "urlopen", fake_urlopen)

    client = WFSClient("http://features.example/wfs")
    capabilities = client.get_capabilities()
    rows = client.list_feature_types()

    assert capabilities["online"] is True
    assert capabilities["service"] == "WFS"
    assert capabilities["title"] == "S3M Coalition WFS"
    assert len(rows) == 1
    assert rows[0]["name"] == "s3m:tracks"
    assert rows[0]["default_crs"] == "EPSG:4326"


def test_wfs_get_feature_graceful_failure_returns_empty(monkeypatch) -> None:
    def failing_urlopen(req, timeout=8.0):  # noqa: ARG001
        _ = req
        raise error.URLError("offline")

    monkeypatch.setattr(wfs_module.request, "urlopen", failing_urlopen)
    client = WFSClient("http://features.example/wfs")

    payload = client.get_feature("s3m:tracks", bbox=(46.0, 24.0, 48.0, 26.0), max_features=50)
    assert payload == ""


def test_geojson_adapter_roundtrip_tracks_and_nvg() -> None:
    adapter = GeoJSONAdapter()
    tracks = [
        {
            "track_id": "trk-1",
            "callsign": "S3M-01",
            "position": [46.7, 24.7, 500.0],
            "affiliation": "friendly",
            "heading": 45.0,
            "speed": 60.0,
        }
    ]

    geojson = adapter.tracks_to_geojson(tracks)
    parsed_tracks = adapter.geojson_to_tracks(geojson)
    nvg_xml = adapter.geojson_to_nvg(geojson)
    nvg_geojson = adapter.nvg_to_geojson(
        {
            "elements": [
                {"type": "point", "lon": 46.7, "lat": 24.7, "alt": 500.0, "properties": {"label": "trk-1"}},
                {"type": "line", "points": [[46.6, 24.6, 0.0], [46.8, 24.8, 0.0]]},
            ]
        }
    )

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1
    assert parsed_tracks[0]["track_id"] == "trk-1"
    assert "<nvg" in nvg_xml and "<point" in nvg_xml
    assert nvg_geojson["type"] == "FeatureCollection"
    assert len(nvg_geojson["features"]) == 2


def test_geojson_adapter_mission_to_geojson() -> None:
    adapter = GeoJSONAdapter()
    mission = {
        "mission_id": "mission-1",
        "waypoints": [{"id": "wp-1", "position": [46.1, 24.1, 0.0]}],
        "objectives": [{"id": "obj-1", "position": [46.2, 24.2, 0.0], "priority": "high"}],
        "path": [[46.1, 24.1, 0.0], [46.2, 24.2, 0.0]],
    }
    geojson = adapter.mission_to_geojson(mission)
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 3


def test_ogc_routes_status_and_transforms(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(ogc_router)
    client = TestClient(app)

    resp = client.get("/interop/ogc/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "wms_servers" in body
    assert "wfs_servers" in body
    assert body["default_srs"] == "EPSG:4326"

    tracks_resp = client.post(
        "/interop/ogc/geojson/tracks",
        json={"tracks": [{"track_id": "trk-9", "position": [46.5, 24.5, 0.0], "callsign": "S3M-9"}]},
    )
    assert tracks_resp.status_code == 200
    assert tracks_resp.json()["type"] == "FeatureCollection"

    to_tracks_resp = client.post(
        "/interop/ogc/geojson/to-tracks",
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [46.5, 24.5, 0.0]},
                        "properties": {"track_id": "trk-9", "callsign": "S3M-9"},
                    }
                ],
            }
        },
    )
    assert to_tracks_resp.status_code == 200
    assert to_tracks_resp.json()["total"] == 1

    to_nvg_resp = client.post(
        "/interop/ogc/geojson/to-nvg",
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [46.5, 24.5, 0.0]},
                        "properties": {"track_id": "trk-9"},
                    }
                ],
            }
        },
    )
    assert to_nvg_resp.status_code == 200
    assert "<nvg" in to_nvg_resp.json()["nvg_xml"]

    # Exercise WMS/WFS route adapters through monkeypatched clients.
    monkeypatch.setitem(_OGC_CONFIG, "wms_servers", ["http://maps.example/wms"])
    monkeypatch.setitem(_OGC_CONFIG, "wfs_servers", ["http://features.example/wfs"])
    monkeypatch.setattr(WMSClient, "get_capabilities", lambda self: {"service": "WMS", "layers": [], "online": False})
    monkeypatch.setattr(WFSClient, "get_capabilities", lambda self: {"service": "WFS", "feature_types": [], "online": False})

    wms_resp = client.get("/interop/ogc/wms/0/capabilities")
    assert wms_resp.status_code == 200
    assert wms_resp.json()["service"] == "WMS"

    wfs_resp = client.get("/interop/ogc/wfs/0/capabilities")
    assert wfs_resp.status_code == 200
    assert wfs_resp.json()["service"] == "WFS"

