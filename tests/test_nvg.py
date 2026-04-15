"""Tests for NATO Vector Graphics (NVG) overlay interoperability."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from services.interop.models import ForceStructure, ORBATUnit
from services.interop.nvg import NVGBuilder, NVGOverlayExchange, NVGParser


def _sample_track(track_id: str, lat: float, lon: float) -> dict:
    return {
        "id": track_id,
        "lat": lat,
        "lon": lon,
        "sidc": "10031012000000000000",
        "callsign": track_id.upper(),
        "speed": 15.5,
        "heading": 92.0,
    }


def _sample_mission_layer() -> dict:
    return {
        "missionId": "mission-001",
        "waypoints": [
            {"id": "WP-1", "lat": 50.45, "lon": 30.52},
            {"id": "WP-2", "lat": 50.46, "lon": 30.53},
            {"id": "WP-3", "lat": 50.47, "lon": 30.54},
        ],
        "phaseLines": [
            {
                "id": "PL-ALPHA",
                "label": "Phase Line Alpha",
                "points": [(50.45, 30.52), (50.48, 30.56)],
                "style": "stroke:red",
            }
        ],
        "objectives": [
            {
                "id": "OBJ-BRAVO",
                "label": "Objective Bravo",
                "points": [(50.40, 30.45), (50.41, 30.46), (50.39, 30.47)],
                "style": "fill:blue;opacity:0.3",
            }
        ],
    }


def _nvg_namespace(root: ET.Element) -> str:
    if root.tag.startswith("{") and "}" in root.tag:
        return root.tag[1 : root.tag.index("}")]
    return ""


def test_build_nvg_point_with_sidc():
    builder = NVGBuilder()
    builder.add_point(
        lat=50.4501,
        lon=30.5234,
        symbol_sidc="10031012000000000000",
        label="EAGLE-11",
        speed=20.2,
        course=45.0,
    )
    xml = builder.build()
    root = ET.fromstring(xml)
    ns = {"nvg": "http://tide.act.nato.int/schemas/2012/10/nvg"}
    point = root.find("nvg:point", ns)
    assert point is not None
    assert point.attrib["symbol"] == "10031012000000000000"
    assert point.attrib["label"] == "EAGLE-11"


def test_build_nvg_from_tracks():
    tracks = [_sample_track("trk-1", 50.45, 30.52), _sample_track("trk-2", 50.46, 30.53)]
    builder = NVGBuilder()
    parser = NVGParser()
    xml = builder.from_tracks(tracks)
    parsed = parser.parse(xml)
    parsed_tracks = parser.to_tracks(parsed)
    assert len(parsed_tracks) == 2
    assert parsed_tracks[0]["position"][0] == tracks[0]["lat"]
    assert parsed_tracks[0]["position"][1] == tracks[0]["lon"]
    assert parsed_tracks[1]["position"][0] == tracks[1]["lat"]
    assert parsed_tracks[1]["position"][1] == tracks[1]["lon"]


def test_build_nvg_from_mission_layer():
    layer = _sample_mission_layer()
    builder = NVGBuilder()
    parser = NVGParser()
    xml = builder.from_mission_layer(layer)
    parsed = parser.parse(xml)
    assert len(parsed["polylines"]) >= 2  # waypoints polyline + phase line
    labels = [item.get("label", "") for item in parsed["polylines"]]
    assert "Phase Line Alpha" in labels
    assert any(label.startswith("Waypoints") for label in labels)


def test_parse_nvg_standard_document():
    xml = """
<nvg xmlns="http://tide.act.nato.int/schemas/2012/10/nvg" version="2.0">
  <point symbol="10031012000000000000" lat="50.45" lon="30.52" label="EAGLE-11">
    <ExtendedData>
      <SimpleData name="speed">12.5</SimpleData>
      <SimpleData name="course">90</SimpleData>
    </ExtendedData>
  </point>
  <polyline points="50.45,30.52 50.46,30.53" label="Phase Line Alpha" style="stroke:red"/>
  <polygon points="50.40,30.45 50.41,30.46 50.39,30.47" label="Objective Bravo" style="fill:blue;opacity:0.3"/>
  <circle cx="50.47" cy="30.55" r="500" label="Engagement Zone"/>
</nvg>
""".strip()
    parser = NVGParser()
    parsed = parser.parse(xml)
    assert len(parsed["points"]) == 1
    assert len(parsed["polylines"]) == 1
    assert len(parsed["polygons"]) == 1
    assert len(parsed["circles"]) == 1
    assert parsed["points"][0]["label"] == "EAGLE-11"
    assert parsed["points"][0]["speed"] == 12.5
    assert parsed["points"][0]["course"] == 90.0


def test_nvg_namespace_correct():
    builder = NVGBuilder()
    builder.add_point(50.45, 30.52, "10031012000000000000", "EAGLE-11")
    xml = builder.build()
    root = ET.fromstring(xml)
    assert _nvg_namespace(root) == "http://tide.act.nato.int/schemas/2012/10/nvg"


def test_cop_overlay_contains_all_tracks():
    tracks = [
        _sample_track("trk-1", 50.45, 30.52),
        _sample_track("trk-2", 50.46, 30.53),
        _sample_track("trk-3", 50.47, 30.54),
    ]
    mission_layer = _sample_mission_layer()
    exchange = NVGOverlayExchange(config={"nvg": {"outbox_dir": "data/interop/nvg_outbox_tests/"}})
    xml = exchange.publish_cop_overlay(tracks=tracks, mission_layers=[mission_layer])
    parsed = exchange.parser.parse(xml)
    assert len(parsed["points"]) == len(tracks)


def test_builder_from_orbat_creates_points():
    force = ForceStructure(
        force_id="force-1",
        force_name="Blue Force",
        affiliation="friendly",
        country_code=178,
        units=[
            ORBATUnit(
                unit_id="u1",
                name="1st Battalion",
                designation="1 BN",
                echelon="battalion",
                unit_type="infantry",
                affiliation="friendly",
                parent_unit_id=None,
                subordinate_ids=[],
                country_code=178,
                nato_symbol="",
                strength=500,
                equipment=[],
                position=(50.45, 30.52),
                commander=None,
            )
        ],
    )
    builder = NVGBuilder()
    parser = NVGParser()
    xml = builder.from_orbat(force)
    parsed = parser.parse(xml)
    assert len(parsed["points"]) == 1
    assert parsed["points"][0]["label"] == "1 BN"
