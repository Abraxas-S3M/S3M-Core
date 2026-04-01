#!/usr/bin/env python3
"""Tests for Layer 09 geospatial processing utilities."""

from __future__ import annotations

import json

from services.sensor_analytics.geospatial import GeospatialProcessor


def test_haversine_riyadh_jeddah_sanity() -> None:
    geo = GeospatialProcessor()
    # Riyadh (24.7136, 46.6753) to Jeddah (21.4858, 39.1925) ~ 845-955km depending method.
    dist = geo.haversine_distance(24.7136, 46.6753, 21.4858, 39.1925)
    assert 800.0 <= dist <= 1000.0


def test_point_in_polygon_square() -> None:
    geo = GeospatialProcessor()
    polygon = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0)]
    assert geo.point_in_polygon(5.0, 5.0, polygon)
    assert not geo.point_in_polygon(15.0, 5.0, polygon)


def test_geo_local_round_trip() -> None:
    geo = GeospatialProcessor()
    lat, lon = 25.0, 50.0
    x, y = geo.geo_to_local(lat, lon, 24.5, 49.5)
    lat2, lon2 = geo.local_to_geo(x, y, 24.5, 49.5)
    assert abs(lat - lat2) < 0.01
    assert abs(lon - lon2) < 0.01


def test_export_geojson(tmp_path) -> None:
    geo = GeospatialProcessor()
    fp = tmp_path / "out.geojson"
    feature = geo.create_geojson_feature((50.0, 25.0), {"name": "contact"})
    geo.export_geojson([feature], str(fp))
    payload = json.loads(fp.read_text(encoding="utf-8"))
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
