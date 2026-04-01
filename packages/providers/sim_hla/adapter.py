"""Simulation-only IEEE-1516 HLA adapter with CERTI/stub operation modes."""

from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest
from packages.providers.sim_hla.config import HLAConfig
from packages.providers.sim_hla.coordinates import Phase16CoordinateConverter
from packages.providers.sim_hla.fom_manager import FOMManager
from packages.providers.sim_hla.normalizer import HLANormalizer


class HLAAdapter(ProviderAdapter):
    provider_id = "sim-hla"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = HLAConfig()
        self.normalizer = HLANormalizer()
        self.fom_manager = FOMManager(self.config.fom_path)
        self._converter = Phase16CoordinateConverter()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "sim-hla" / "fixtures"

        self._runtime_mode = "stub"
        self._rti = None
        self._federation_name = self.config.default_federation_name
        self._federate_name = self.config.default_federate_name
        self._joined = False
        self._published_objects: dict[str, dict[str, Any]] = {}
        self._incoming_updates: list[dict[str, Any]] = []
        self._interactions_sent = 0
        self._interactions_received = 0

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="C4I_INTEROP",
            tier="OPEN_STANDARD",
            auth_type="none",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=[],
            description=(
                "IEEE-1516 HLA federation protocol for joint exercise simulation. "
                "SIMULATION ONLY - no live command-and-control."
            ),
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            self._runtime_mode = "stub"
            return True

        # Tactical context: HLA federation hookup is optional in lab rehearsal;
        # stub mode preserves deterministic interoperability testing offline.
        if self.config.rti_type.lower() == "stub":
            self._runtime_mode = "stub"
            return True
        try:
            import certi  # type: ignore

            self._rti = certi.RTIAmbassador()
            self._runtime_mode = "certi"
            return True
        except Exception:
            pass

        try:
            with socket.create_connection((self.config.certi_host, int(self.config.certi_port)), timeout=0.8):
                self._runtime_mode = self.config.rti_type.lower()
                return True
        except Exception:
            self._runtime_mode = "stub"
            return True

    def create_federation(self, name: str | None = None, fom_path: str | None = None) -> dict[str, Any]:
        federation_name = name or self.config.default_federation_name
        fom_file = fom_path or self.config.fom_path
        if not Path(fom_file).exists():
            self.fom_manager.generate_s3m_fom()

        created = True
        if self._runtime_mode == "certi" and self._rti is not None:
            try:
                self._rti.createFederationExecution(federation_name, fom_file)
            except Exception:
                created = True
        self._federation_name = federation_name
        return {
            "federation_name": federation_name,
            "fom": fom_file,
            "created": created,
            "mode": self._runtime_mode,
        }

    def join_federation(self, federation_name: str | None = None, federate_name: str | None = None) -> dict[str, Any]:
        self._federation_name = federation_name or self._federation_name
        self._federate_name = federate_name or self._federate_name
        self._joined = True
        published = sorted(self.config.object_classes.keys())
        subscribed = sorted(self.config.object_classes.keys())
        return {
            "federate_name": self._federate_name,
            "federation_name": self._federation_name,
            "joined": True,
            "published_classes": published,
            "subscribed_classes": subscribed,
        }

    @staticmethod
    def _next_id(counter: int) -> str:
        return f"hla-obj-{counter:04d}"

    @staticmethod
    def _map_entity_type(entity_type: str) -> str:
        key = str(entity_type).strip().lower()
        mapping = {
            "aircraft": "Aircraft",
            "uav": "Aircraft",
            "copter": "Aircraft",
            "plane": "Aircraft",
            "groundvehicle": "GroundVehicle",
            "ground_vehicle": "GroundVehicle",
            "ugv": "GroundVehicle",
            "surfacevessel": "SurfaceVessel",
            "surface_vessel": "SurfaceVessel",
            "ship": "SurfaceVessel",
            "munition": "Munition",
            "sensor": "Sensor",
        }
        return mapping.get(key, entity_type if entity_type in {"Aircraft", "GroundVehicle", "SurfaceVessel", "Munition", "Sensor"} else "Aircraft")

    def publish_entity(
        self,
        entity_type: str,
        entity_name: str,
        position: tuple[float, float, float],
        velocity: tuple[float, float, float] | None = None,
        force_id: int = 1,
        damage: int = 0,
    ) -> dict[str, Any]:
        if not self._joined:
            self.join_federation()
        cls = self._map_entity_type(entity_type)
        object_id = self._next_id(len(self._published_objects) + 1)
        lat, lon, alt = float(position[0]), float(position[1]), float(position[2])
        x, y, z = self._converter.lla_to_ecef(lat, lon, alt)
        self._published_objects[object_id] = {
            "object_id": object_id,
            "entity_type": cls,
            "name": entity_name,
            "world_location": {"x": x, "y": y, "z": z},
            "velocity": {"x": float((velocity or (0.0, 0.0, 0.0))[0]), "y": float((velocity or (0.0, 0.0, 0.0))[1]), "z": float((velocity or (0.0, 0.0, 0.0))[2])},
            "force_id": int(force_id),
            "damage_state": int(damage),
            "updated_at": time.time(),
        }
        return {"object_id": object_id, "entity_type": cls, "entity_name": entity_name, "published": True}

    def update_entity(
        self,
        object_id: str,
        position: tuple[float, float, float] | None = None,
        velocity: tuple[float, float, float] | None = None,
        damage: int | None = None,
    ) -> dict[str, Any]:
        item = self._published_objects.get(object_id)
        if not item:
            return {"object_id": object_id, "updated": False, "reason": "not_found"}
        if position is not None:
            x, y, z = self._converter.lla_to_ecef(float(position[0]), float(position[1]), float(position[2]))
            item["world_location"] = {"x": x, "y": y, "z": z}
        if velocity is not None:
            item["velocity"] = {"x": float(velocity[0]), "y": float(velocity[1]), "z": float(velocity[2])}
        if damage is not None:
            item["damage_state"] = int(damage)
        item["updated_at"] = time.time()
        return {"object_id": object_id, "updated": True}

    def send_interaction(self, interaction_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
        self._interactions_sent += 1
        payload = {"interaction_type": interaction_type, "parameters": dict(parameters), "timestamp": time.time()}
        self._incoming_updates.append({"type": "interaction", "data": payload})
        return {"interaction_type": interaction_type, "sent": True, "parameters": dict(parameters)}

    def receive_updates(self) -> list[dict[str, Any]]:
        updates = list(self._incoming_updates)
        self._incoming_updates = []
        out: list[dict[str, Any]] = []
        for item in updates:
            if item.get("type") == "object_update":
                out.append({"type": "object_update", "data": self.normalizer.normalize_object_update(item.get("data", {}))})
            else:
                self._interactions_received += 1
                out.append({"type": "interaction", "data": self.normalizer.normalize_interaction(item.get("data", {}))})
        return out

    def resign_federation(self) -> dict[str, Any]:
        self._joined = False
        return {"federate_name": self._federate_name, "resigned": True}

    def destroy_federation(self) -> dict[str, Any]:
        self._published_objects.clear()
        self._incoming_updates.clear()
        return {"federation_name": self._federation_name, "destroyed": True}

    def sync_from_phase7(self, sim_state: dict[str, Any]) -> int:
        entities = list(sim_state.get("entities", []))
        count = 0
        for entity in entities:
            name = str(entity.get("entity_id", entity.get("name", f"entity-{count+1}")))
            entity_type = self._map_entity_type(str(entity.get("entity_type", "Aircraft")))
            pos = entity.get("position", (0.0, 0.0, 0.0))
            if isinstance(pos, dict):
                position = (float(pos.get("lat", 0.0)), float(pos.get("lon", 0.0)), float(pos.get("alt", 0.0)))
            else:
                position = (float(pos[0]), float(pos[1]), float(pos[2]))
            vel = entity.get("velocity", (0.0, 0.0, 0.0))
            if isinstance(vel, dict):
                velocity = (float(vel.get("x", 0.0)), float(vel.get("y", 0.0)), float(vel.get("z", 0.0)))
            else:
                velocity = (float(vel[0]), float(vel[1]), float(vel[2]))
            affiliation = str(entity.get("affiliation", "friendly")).lower()
            force_id = 1 if affiliation in {"friendly", "blue", "allied"} else 2 if affiliation in {"hostile", "enemy", "red"} else 3
            self.publish_entity(entity_type=entity_type, entity_name=name, position=position, velocity=velocity, force_id=force_id)
            count += 1
        return count

    def sync_from_phase16_dis(self, dis_entities: dict[str, Any]) -> int:
        rows = dis_entities.values() if isinstance(dis_entities, dict) else []
        count = 0
        for entity in rows:
            hla_entity = self.normalizer.dis_to_hla_entity(entity)
            world = hla_entity.get("world_location", {})
            lat, lon, alt = self._converter.ecef_to_lla(float(world.get("x", 0.0)), float(world.get("y", 0.0)), float(world.get("z", 0.0)))
            vel = hla_entity.get("velocity", {"x": 0.0, "y": 0.0, "z": 0.0})
            self.publish_entity(
                entity_type=str(hla_entity.get("entity_type", "Aircraft")),
                entity_name=str(hla_entity.get("name", "dis-entity")),
                position=(lat, lon, alt),
                velocity=(float(vel.get("x", 0.0)), float(vel.get("y", 0.0)), float(vel.get("z", 0.0))),
                force_id=int(hla_entity.get("force_id", 3)),
            )
            count += 1
        return count

    def get_federation_status(self) -> dict[str, Any]:
        return {
            "federation_name": self._federation_name,
            "joined": self._joined,
            "mode": self._runtime_mode,
            "published_objects": len(self._published_objects),
            "received_objects": len([u for u in self._incoming_updates if u.get("type") == "object_update"]),
            "interactions_sent": self._interactions_sent,
            "interactions_received": self._interactions_received,
            "time_step": float(self.config.time_step_seconds),
        }

    def fetch(self, params: dict[str, Any]) -> Any:
        action = str(params.get("action", "status"))
        if action == "receive":
            return self.receive_updates()
        if action == "status":
            return self.get_federation_status()
        return self.get_federation_status()

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "interaction_type" in raw_data:
            return self.normalizer.normalize_interaction(raw_data)
        if isinstance(raw_data, dict) and ("world_location" in raw_data or "position_ecef" in raw_data):
            return self.normalizer.normalize_object_update(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "mode": self._runtime_mode,
            "joined": self._joined,
            "federation": self._federation_name,
        }
