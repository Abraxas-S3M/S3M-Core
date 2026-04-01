from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from packages.providers.sim_hla.adapter import HLAAdapter
from packages.providers.sim_hla.fom_manager import FOMManager
from packages.providers.sim_hla.normalizer import HLANormalizer
from packages.providers.sim_hla.coordinates import Phase16CoordinateConverter


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_manifest_correct() -> None:
    manifest = HLAAdapter(mode="airgapped").get_manifest()
    assert manifest.provider_id == "sim-hla"
    assert manifest.category == "C4I_INTEROP"
    assert manifest.tier == "OPEN_STANDARD"
    assert manifest.auth_type == "none"
    assert "simulation only" in manifest.description.lower()


def test_stub_mode_always_available() -> None:
    adapter = HLAAdapter(mode="airgapped")
    assert adapter.validate_credentials() is True
    assert adapter.health_check()["mode"] == "stub"


def test_create_federation_stub() -> None:
    adapter = HLAAdapter(mode="airgapped")
    adapter.validate_credentials()
    out = adapter.create_federation()
    assert out["created"] is True
    assert out["mode"] == "stub"


def test_join_federation_stub() -> None:
    adapter = HLAAdapter(mode="airgapped")
    adapter.validate_credentials()
    out = adapter.join_federation()
    assert out["joined"] is True
    assert len(out["published_classes"]) >= 3
    assert len(out["subscribed_classes"]) >= 3


def test_publish_entity_structure() -> None:
    adapter = HLAAdapter(mode="airgapped")
    adapter.join_federation()
    out = adapter.publish_entity("Aircraft", "Saudi_F15_01", (24.71, 46.68, 612.0))
    assert {"object_id", "entity_type", "entity_name", "published"}.issubset(out.keys())


def test_coordinate_conversion_reuses_phase16() -> None:
    converter = Phase16CoordinateConverter()
    x1, y1, z1 = converter.lla_to_ecef(24.71, 46.68, 612.0)
    adapter = HLAAdapter(mode="airgapped")
    pub = adapter.publish_entity("Aircraft", "A", (24.71, 46.68, 612.0))
    obj = adapter._published_objects[pub["object_id"]]
    world = obj["world_location"]
    assert abs(world["x"] - x1) < 1e-3
    assert abs(world["y"] - y1) < 1e-3
    assert abs(world["z"] - z1) < 1e-3


def test_normalize_object_to_s3m_entity() -> None:
    normalizer = HLANormalizer()
    update = json.loads((FIXTURE_DIR / "object_update_aircraft.json").read_text(encoding="utf-8"))
    out = normalizer.normalize_object_update(update)
    assert out["source"] == "hla"
    assert "position" in out and len(out["position"]) == 3


def test_normalize_interaction_to_event() -> None:
    normalizer = HLANormalizer()
    interaction = json.loads((FIXTURE_DIR / "interaction_weapon_fire.json").read_text(encoding="utf-8"))
    out = normalizer.normalize_interaction(interaction)
    assert out["event_type"] == "fire"
    assert out["source"] == "hla"


def test_hla_dis_bridge() -> None:
    normalizer = HLANormalizer()
    hla_entity = {
        "object_id": "obj1",
        "world_location": {"x": 3962090.0, "y": 4210900.0, "z": 2659200.0},
        "velocity": {"x": 30.0, "y": 0.0, "z": 0.0},
        "force_id": 1,
        "name": "Blue1",
    }
    dis_entity = normalizer.hla_to_dis_entity(hla_entity)
    hla_back = normalizer.dis_to_hla_entity(dis_entity)
    assert "position" in dis_entity
    assert "world_location" in hla_back
    assert hla_back["source"] == "dis"


def test_fom_generation() -> None:
    manager = FOMManager("configs/interop/s3m_fom.xml")
    xml = manager.generate_s3m_fom()
    ok, errors = manager.validate_fom(xml)
    assert ok is True
    assert errors == []
    assert "Aircraft" in xml and "WeaponFire" in xml


def test_sync_from_phase7() -> None:
    adapter = HLAAdapter(mode="airgapped")
    count = adapter.sync_from_phase7(
        {
            "entities": [
                {"entity_id": "e1", "entity_type": "Aircraft", "position": (24.71, 46.68, 620.0), "velocity": (10, 0, 0)},
                {"entity_id": "e2", "entity_type": "GroundVehicle", "position": (24.72, 46.69, 610.0), "velocity": (3, 0, 0)},
            ]
        }
    )
    assert count == 2


def test_federation_status_structure() -> None:
    status = HLAAdapter(mode="airgapped").get_federation_status()
    assert {
        "federation_name",
        "joined",
        "mode",
        "published_objects",
        "received_objects",
        "interactions_sent",
        "interactions_received",
        "time_step",
    }.issubset(status.keys())


def test_fetch_airgapped() -> None:
    adapter = HLAAdapter(mode="airgapped")
    adapter.validate_credentials()
    assert adapter.fetch({"action": "status"})["mode"] == "stub"
