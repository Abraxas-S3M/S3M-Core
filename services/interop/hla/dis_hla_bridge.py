"""Bridge logic between DIS entities and HLA federation objects."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from services.interop.hla.federate_adapter import HLAFederateAdapter
from services.interop.models import DISEntityType, DISWorldCoordinate


class DISHLABridge:
    """Bidirectional DIS/HLA bridge for coalition LVC synchronization."""

    def __init__(self, federate_adapter: HLAFederateAdapter):
        self.federate = federate_adapter

    def sync_from_dis(self, dis_entity: dict) -> None:
        if not isinstance(dis_entity, dict):
            return

        class_name = self._map_dis_entity_to_hla_class(dis_entity.get("entity_type"))
        object_handle = self._to_object_handle(dis_entity.get("entity_id", 0))
        position = self._extract_position(dis_entity.get("position", {}))
        velocity = self._extract_velocity(dis_entity.get("velocity", {}))
        marking = str(dis_entity.get("marking", dis_entity.get("name", f"{class_name}-{object_handle}")))
        attributes = {
            "Position": position,
            "Velocity": velocity,
            "Marking": marking,
            "ForceIdentifier": str(dis_entity.get("force_id", dis_entity.get("affiliation", "unknown"))),
        }
        self.federate.update_object(class_name=class_name, object_handle=object_handle, attributes=attributes)

    def sync_from_hla(self, hla_object: dict) -> dict:
        if not isinstance(hla_object, dict):
            return {}
        attributes = hla_object.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}

        lat, lon, alt = self._decode_position(attributes.get("Position", "0,0,0"))
        class_name = str(hla_object.get("class_name", "Unknown"))
        object_handle = str(hla_object.get("object_handle", "0"))

        return {
            "unit_id": f"hla-{class_name}-{object_handle}",
            "role": class_name.lower(),
            "status": str(attributes.get("DamageState", "active")).lower(),
            "position": [lat, lon, alt],
        }

    def sync_from_phase7_sim(self, sim_state: dict) -> None:
        if not isinstance(sim_state, dict):
            return
        entities: Iterable[Any] = sim_state.get("entities", [])
        if not isinstance(entities, list):
            return

        # Tactical context: phase-7 synthetic units are mirrored to HLA so coalition
        # federates receive synchronized training battlespace updates.
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            class_name = self._map_phase7_entity_to_hla_class(entity)
            object_handle = self._to_object_handle(entity.get("entity_id", entity.get("id", 0)))
            attributes = {
                "Position": entity.get("position", entity.get("geo", {"lat": 0.0, "lon": 0.0, "alt": 0.0})),
                "Velocity": entity.get("velocity", {"x": 0.0, "y": 0.0, "z": 0.0}),
                "Marking": str(entity.get("marking", entity.get("name", f"phase7-{object_handle}"))),
                "ForceIdentifier": str(entity.get("affiliation", "friendly")),
            }
            self.federate.update_object(class_name=class_name, object_handle=object_handle, attributes=attributes)

    @staticmethod
    def _to_object_handle(value: Any) -> int:
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return max(1, sum(ord(ch) for ch in str(value)) % 65535)

    def _map_dis_entity_to_hla_class(self, entity_type: Any) -> str:
        if isinstance(entity_type, DISEntityType):
            return self._map_domain_to_class(int(entity_type.domain))
        if isinstance(entity_type, dict):
            domain = int(entity_type.get("domain", 1))
            return self._map_domain_to_class(domain)
        text = str(entity_type or "").upper()
        if "AIR" in text or "UAV" in text or "AIRCRAFT" in text:
            return "Aircraft"
        if "VESSEL" in text or "SHIP" in text or "SURFACE" in text:
            return "SurfaceVessel"
        return "GroundVehicle"

    @staticmethod
    def _map_domain_to_class(domain: int) -> str:
        if domain == 2:
            return "Aircraft"
        if domain == 3:
            return "SurfaceVessel"
        return "GroundVehicle"

    def _map_phase7_entity_to_hla_class(self, entity: Dict[str, Any]) -> str:
        entity_type = str(entity.get("entity_type", entity.get("type", ""))).upper()
        if "UAV" in entity_type or "AIR" in entity_type:
            return "Aircraft"
        if "SHIP" in entity_type or "VESSEL" in entity_type or "SURFACE" in entity_type:
            return "SurfaceVessel"
        return "GroundVehicle"

    @staticmethod
    def _extract_velocity(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                "x": float(value.get("x", value.get("vx", 0.0))),
                "y": float(value.get("y", value.get("vy", 0.0))),
                "z": float(value.get("z", value.get("vz", 0.0))),
            }
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return {"x": float(value[0]), "y": float(value[1]), "z": float(value[2])}
        return {"x": 0.0, "y": 0.0, "z": 0.0}

    @staticmethod
    def _extract_position(value: Any) -> Any:
        if isinstance(value, DISWorldCoordinate):
            lat, lon, alt = value.to_lat_lon_alt()
            return {"lat": lat, "lon": lon, "alt": alt}
        if isinstance(value, dict):
            if {"lat", "lon"}.issubset(value.keys()):
                return {
                    "lat": float(value.get("lat", value.get("latitude", 0.0))),
                    "lon": float(value.get("lon", value.get("longitude", 0.0))),
                    "alt": float(value.get("alt", value.get("altitude", 0.0))),
                }
            if {"x", "y", "z"}.issubset(value.keys()):
                return value
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return {"lat": float(value[0]), "lon": float(value[1]), "alt": float(value[2])}
        return {"lat": 0.0, "lon": 0.0, "alt": 0.0}

    @staticmethod
    def _decode_position(value: Any) -> tuple[float, float, float]:
        if isinstance(value, str):
            parts = [chunk.strip() for chunk in value.split(",")]
            if len(parts) >= 3:
                try:
                    return (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    return (0.0, 0.0, 0.0)
        if isinstance(value, dict):
            return (
                float(value.get("lat", value.get("latitude", 0.0))),
                float(value.get("lon", value.get("longitude", 0.0))),
                float(value.get("alt", value.get("altitude", 0.0))),
            )
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return (float(value[0]), float(value[1]), float(value[2]))
        return (0.0, 0.0, 0.0)
