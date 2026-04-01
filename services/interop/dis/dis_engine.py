"""Top-level DIS engine orchestrating protocol, coordinates, and networking."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from services.interop.dis.coordinate_converter import DISCoordinateConverter
from services.interop.dis.dead_reckoning import DISDeadReckoning
from services.interop.dis.network_manager import DISNetworkManager
from services.interop.dis.pdu_factory import DISPDUFactory
from services.interop.models import (
    DISEntityID,
    DISEntityType,
    DISLinearVelocity,
    DISOrientation,
    DISWorldCoordinate,
)


class DISEngine:
    """Phase 16 DIS implementation that can back Phase 10 adapter calls."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.factory = DISPDUFactory()
        self.coordinates = DISCoordinateConverter()
        self.dead_reckoning = DISDeadReckoning()
        self.network = DISNetworkManager(
            broadcast_address=self.config.get("broadcast_address", "255.255.255.255"),
            port=int(self.config.get("port", 3000)),
            exercise_id=int(self.config.get("exercise_id", 1)),
        )
        self.exercise_id = int(self.config.get("exercise_id", 1))
        self.site_id = int(self.config.get("site_id", 1))
        self.application_id = int(self.config.get("application_id", 1))
        self._known_entities: Dict[str, dict] = {}

    def start(self, exercise_id: int = 1, broadcast: str = "255.255.255.255", port: int = 3000) -> bool:
        self.exercise_id = int(exercise_id)
        self.network.exercise_id = self.exercise_id
        self.network.broadcast_address = str(broadcast)
        self.network.port = int(port)
        return self.network.start()

    def stop(self):
        self.network.stop()

    def _to_entity_id(self, entity: dict) -> DISEntityID:
        raw_id = entity.get("entity_id", 0)
        if isinstance(raw_id, str):
            try:
                entity_id = int(raw_id)
            except ValueError:
                entity_id = sum(ord(ch) for ch in raw_id) % 65535
        else:
            entity_id = int(raw_id)
        return DISEntityID(self.site_id, self.application_id, entity_id)

    @staticmethod
    def _force_from_affiliation(affiliation: str) -> int:
        val = str(affiliation or "").strip().lower()
        if val in {"friendly", "blue", "allied"}:
            return 1
        if val in {"hostile", "enemy", "red"}:
            return 2
        return 3

    @staticmethod
    def _entity_type_from_payload(payload: dict) -> DISEntityType:
        if not isinstance(payload, dict):
            return DISEntityType(1, 1, 178, 1, 0, 0, 0)
        kind = int(payload.get("kind", 1))
        domain = int(payload.get("domain", 1))
        country = int(payload.get("country", 178))
        category = int(payload.get("category", 1))
        subcategory = int(payload.get("subcategory", 0))
        specific = int(payload.get("specific", 0))
        extra = int(payload.get("extra", 0))
        return DISEntityType(kind, domain, country, category, subcategory, specific, extra)

    def publish_entity(self, entity: dict) -> bool:
        # Tactical context: simulator entities are converted to DIS ECEF to maintain
        # coordinate consistency across coalition federates.
        entity_id = self._to_entity_id(entity)
        entity_type = self._entity_type_from_payload(entity.get("entity_type", {}))
        pos = entity.get("position", {})
        if isinstance(pos, (tuple, list)) and len(pos) >= 3:
            lat, lon, alt = float(pos[0]), float(pos[1]), float(pos[2])
        else:
            lat = float(pos.get("lat", pos.get("latitude", 0.0)))
            lon = float(pos.get("lon", pos.get("longitude", 0.0)))
            alt = float(pos.get("alt", pos.get("altitude", 0.0)))
        ecef = self.coordinates.lla_to_dis(lat, lon, alt)
        orient_payload = entity.get("orientation", {})
        heading = float(orient_payload.get("heading", orient_payload.get("psi", 0.0)))
        pitch = float(orient_payload.get("pitch", orient_payload.get("theta", 0.0)))
        roll = float(orient_payload.get("roll", orient_payload.get("phi", 0.0)))
        orientation = self.coordinates.heading_to_dis_orientation(
            heading_deg=heading,
            pitch_deg=pitch,
            roll_deg=roll,
            lat_deg=lat,
            lon_deg=lon,
        )
        vel = entity.get("velocity", {})
        velocity = DISLinearVelocity(float(vel.get("x", 0.0)), float(vel.get("y", 0.0)), float(vel.get("z", 0.0)))
        force_id = self._force_from_affiliation(entity.get("affiliation", "friendly"))
        pdu = self.factory.encode_entity_state(
            entity_id=entity_id,
            entity_type=entity_type,
            position=ecef,
            orientation=orientation,
            velocity=velocity,
            force_id=force_id,
            exercise_id=self.exercise_id,
            marking=str(entity.get("marking", entity.get("name", ""))),
        )
        sent = self.network.send_pdu(pdu)
        if sent:
            self._known_entities[f"{entity_id.to_tuple()}"] = {
                "entity_id": entity_id.to_tuple(),
                "entity_type": entity_type,
                "position": (lat, lon, alt),
                "orientation": orientation,
                "velocity": velocity,
                "last_update": time.time(),
            }
        return sent

    def publish_fire(self, shooter, target, munition_type, location) -> bool:
        shooter_id = self._to_entity_id({"entity_id": shooter})
        target_id = self._to_entity_id({"entity_id": target})
        m_type = self._entity_type_from_payload(munition_type if isinstance(munition_type, dict) else {})
        if isinstance(location, (tuple, list)) and len(location) >= 3:
            loc = DISWorldCoordinate.from_lat_lon_alt(float(location[0]), float(location[1]), float(location[2]))
        else:
            loc = DISWorldCoordinate.from_lat_lon_alt(
                float(location.get("lat", 0.0)),
                float(location.get("lon", 0.0)),
                float(location.get("alt", 0.0)),
            )
        pdu = self.factory.encode_fire(shooter_id, target_id, m_type, loc, exercise_id=self.exercise_id)
        return self.network.send_pdu(pdu)

    def publish_detonation(self, shooter, target, location, result) -> bool:
        shooter_id = self._to_entity_id({"entity_id": shooter})
        target_id = self._to_entity_id({"entity_id": target})
        loc = DISWorldCoordinate.from_lat_lon_alt(
            float(location.get("lat", 0.0)),
            float(location.get("lon", 0.0)),
            float(location.get("alt", 0.0)),
        )
        pdu = self.factory.encode_detonation(
            shooter_id,
            target_id,
            loc,
            DISEntityType(2, 1, 178, 1, 0, 0, 0),
            int(result),
            exercise_id=self.exercise_id,
        )
        return self.network.send_pdu(pdu)

    def publish_signal(self, entity, radio_id, data) -> bool:
        entity_id = self._to_entity_id({"entity_id": entity})
        pdu = self.factory.encode_signal(
            entity_id=entity_id,
            radio_id=int(radio_id),
            encoding=1,
            data=bytes(data),
            exercise_id=self.exercise_id,
        )
        return self.network.send_pdu(pdu)

    def receive_entities(self) -> List[dict]:
        rows: List[dict] = []
        for ent_id, state in self.network.get_received_entities().items():
            pos = state.get("position", {})
            if isinstance(pos, DISWorldCoordinate):
                lat, lon, alt = self.coordinates.dis_to_lla(pos)
            else:
                lat, lon, alt = (0.0, 0.0, 0.0)
            rows.append(
                {
                    "entity_id": ent_id[2],
                    "site_id": ent_id[0],
                    "application_id": ent_id[1],
                    "position": {"lat": lat, "lon": lon, "alt": alt},
                    "force_id": state.get("force_id", 3),
                    "marking": state.get("marking", ""),
                    "entity_type": state.get("entity_type", {}).country if state.get("entity_type") else None,
                }
            )
        return rows

    def sync_from_simulation(self, sim_state) -> int:
        entities = getattr(sim_state, "entities", [])
        sent = 0
        for entity in entities:
            payload = entity if isinstance(entity, dict) else getattr(entity, "__dict__", {})
            if hasattr(entity, "entity_type") and not isinstance(payload.get("entity_type"), dict):
                e_val = str(getattr(getattr(entity, "entity_type", None), "value", "UNKNOWN"))
                etype_map = {
                    "FRIENDLY_UAV": {"kind": 1, "domain": 2, "country": 178, "category": 1},
                    "FRIENDLY_UGV": {"kind": 1, "domain": 1, "country": 178, "category": 1},
                    "FRIENDLY_SHIP": {"kind": 1, "domain": 3, "country": 178, "category": 1},
                    "ENEMY_UAV": {"kind": 1, "domain": 2, "country": 0, "category": 1},
                    "ENEMY_UGV": {"kind": 1, "domain": 1, "country": 0, "category": 1},
                    "ENEMY_SHIP": {"kind": 1, "domain": 3, "country": 0, "category": 1},
                }
                payload["entity_type"] = {
                    "kind": etype_map.get(e_val, {}).get("kind", 1),
                    "domain": etype_map.get(e_val, {}).get("domain", 1),
                    "country": etype_map.get(e_val, {}).get("country", 178),
                    "category": etype_map.get(e_val, {}).get("category", 1),
                    "subcategory": 0,
                    "specific": 0,
                    "extra": 0,
                }
                payload["affiliation"] = "hostile" if e_val.startswith("ENEMY_") else "friendly"
            if "position" in payload and isinstance(payload["position"], (tuple, list)):
                p = payload["position"]
                if len(p) >= 3:
                    payload["position"] = {"lat": float(p[0]), "lon": float(p[1]), "alt": float(p[2])}
            if "velocity" in payload and isinstance(payload["velocity"], (tuple, list)):
                v = payload["velocity"]
                if len(v) >= 3:
                    payload["velocity"] = {"x": float(v[0]), "y": float(v[1]), "z": float(v[2])}
            if "heading" in payload and "orientation" not in payload:
                payload["orientation"] = {"heading": float(payload.get("heading", 0.0))}
            if self.publish_entity(payload):
                sent += 1
        return sent

    def sync_to_simulation(self, sim_adapter) -> int:
        entities = self.receive_entities()
        created = 0
        for entity in entities:
            if hasattr(sim_adapter, "spawn_entity"):
                sim_adapter.spawn_entity(entity)
                created += 1
        return created

    def get_dis_entities(self) -> Dict[str, dict]:
        rows = self.network.get_received_entities()
        return {f"{key[0]}-{key[1]}-{key[2]}": value for key, value in rows.items()}

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "exercise_id": self.exercise_id,
            "network": self.network.health_check(),
            "known_entities": len(self._known_entities),
        }
