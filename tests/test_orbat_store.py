"""Unit tests for lightweight ORBAT force structure store."""

from __future__ import annotations

import json

from src.command.orbat_store import ORBATStore


def test_orbat_store_loads_orbat_mapper_feature_collection(tmp_path):
    data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "hq",
                "properties": {
                    "id": "hq",
                    "name": "Brigade HQ",
                    "sidc": "SFGPUCHQ---*****",
                    "equipment": ["AN/PRC-117"],
                },
                "geometry": {"type": "Point", "coordinates": [46.70, 24.70]},
            },
            {
                "type": "Feature",
                "id": "alpha",
                "properties": {
                    "id": "alpha",
                    "name": "Alpha Company",
                    "sidc": "SFGPUCI----*****",
                    "parentId": "hq",
                    "equipment": [{"name": "M2A2 Bradley"}, {"name": "M2A2 Bradley"}],
                },
                "geometry": {"type": "Point", "coordinates": [46.71, 24.71]},
            },
        ],
    }
    src = tmp_path / "orbat_export.json"
    src.write_text(json.dumps(data), encoding="utf-8")

    store = ORBATStore()
    store.load_from_json(str(src))
    hierarchy = store.get_hierarchy()

    assert len(hierarchy) == 1
    assert hierarchy[0]["id"] == "hq"
    assert hierarchy[0]["subordinates"][0]["id"] == "alpha"
    assert hierarchy[0]["position"] == {"lat": 24.7, "lon": 46.7}
    assert store.get_unit("alpha") is not None
    assert store.get_unit("alpha").parent_id == "hq"
    assert store.get_equipment_summary() == {"AN/PRC-117": 1, "M2A2 Bradley": 2}


def test_orbat_store_accepts_flat_units_schema(tmp_path):
    data = {
        "units": [
            {
                "id": "bde",
                "name": "2nd Brigade",
                "sidc": "SFGPUCB----*****",
                "subordinates": ["bn-1"],
                "equipment": [{"type": "Command Vehicle"}],
                "position": {"lat": 24.8, "lon": 46.8},
            },
            {
                "id": "bn-1",
                "name": "1st Battalion",
                "sidc": "SFGPUCAA---*****",
                "equipment": ["M1A2 Abrams"],
            },
        ]
    }
    src = tmp_path / "flat_orbat.json"
    src.write_text(json.dumps(data), encoding="utf-8")

    store = ORBATStore()
    store.load_from_json(str(src))

    hierarchy = store.get_hierarchy()
    assert hierarchy[0]["id"] == "bde"
    assert hierarchy[0]["subordinates"][0]["id"] == "bn-1"
    assert store.get_unit("bn-1").parent_id == "bde"
    assert store.get_equipment_summary() == {
        "Command Vehicle": 1,
        "M1A2 Abrams": 1,
    }
