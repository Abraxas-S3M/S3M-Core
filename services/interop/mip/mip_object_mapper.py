"""Mapping layer between S3M tactical payloads and core MIP entities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from services.interop.models import ForceStructure
from services.interop.mip.mip_data_model import (
    MIPActionTask,
    MIPDataModel,
    MIPLocation,
    MIPObjectItem,
    MIPOperationalInfoGroup,
)


class MIPObjectMapper:
    """Converts S3M tracks, missions, and ORBAT into MIP-compatible entities."""

    _TRACK_TYPE_MAP = {
        "FRIENDLY_UAV": ("equipment", "aircraft"),
        "FRIENDLY_UGV": ("equipment", "ground_vehicle"),
        "FRIENDLY_SHIP": ("equipment", "vessel"),
        "ENEMY_INFANTRY": ("unit", "infantry"),
        "BASE": ("facility", "base"),
    }
    _MISSION_TYPE_MAP = {
        "PATROL": "patrol",
        "INTERCEPT": "attack",
        "ESCORT": "guard",
        "HOLD_POSITION": "defend",
        "RECON": "reconnaissance",
    }
    _MISSION_REVERSE_MAP = {
        "patrol": "PATROL",
        "attack": "INTERCEPT",
        "guard": "ESCORT",
        "defend": "HOLD_POSITION",
        "reconnaissance": "RECON",
    }

    def __init__(self, data_model: Optional[MIPDataModel] = None) -> None:
        self.data_model = data_model or MIPDataModel()
        self._detail_by_object: dict[str, str] = {}

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_float(value: Any, fallback: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _normalize(text: Any) -> str:
        return str(text or "").strip()

    @staticmethod
    def _derive_hostility(track: dict[str, Any], entity_type: str) -> str:
        affiliation = str(track.get("affiliation", "")).strip().lower()
        classification = str(track.get("classification", "")).strip().lower()
        role = str(track.get("role", "")).strip().lower()
        if affiliation in {"friendly", "friend", "allied", "blue"}:
            return "friend"
        if affiliation in {"hostile", "enemy", "red"}:
            return "hostile"
        if affiliation in {"neutral"}:
            return "neutral"
        if classification in {"friendly", "friend"}:
            return "friend"
        if classification in {"hostile", "enemy"}:
            return "hostile"
        if role.startswith("friendly_") or entity_type.startswith("FRIENDLY_"):
            return "friend"
        if role.startswith("enemy_") or entity_type.startswith("ENEMY_"):
            return "hostile"
        return "unknown"

    @staticmethod
    def _extract_track_type(track: dict[str, Any]) -> str:
        for key in ("entity_type", "role", "type"):
            value = str(track.get(key, "")).strip()
            if value:
                return value.replace("-", "_").upper()
        return "UNKNOWN"

    @staticmethod
    def _extract_position(track: dict[str, Any]) -> tuple[float, float, float]:
        position = track.get("position")
        if isinstance(position, (tuple, list)) and len(position) >= 3:
            return float(position[0]), float(position[1]), float(position[2])
        if isinstance(position, dict):
            return (
                float(position.get("lat", position.get("latitude", 0.0))),
                float(position.get("lon", position.get("longitude", 0.0))),
                float(position.get("alt", position.get("altitude", 0.0))),
            )
        return (
            float(track.get("latitude", 0.0)),
            float(track.get("longitude", 0.0)),
            float(track.get("altitude", 0.0)),
        )

    @staticmethod
    def _operational_status(track_status: str) -> str:
        val = str(track_status or "").strip().lower()
        if val in {"destroyed", "killed"}:
            return "destroyed"
        if val in {"damaged", "degraded"}:
            return "degraded"
        return "operational"

    def s3m_track_to_mip(self, track: dict) -> tuple[MIPObjectItem, MIPLocation]:
        raw = dict(track or {})
        track_type = self._extract_track_type(raw)
        category, detail_type = self._TRACK_TYPE_MAP.get(track_type, ("feature", "generic"))
        hostility = self._derive_hostility(raw, track_type)
        name = self._normalize(raw.get("name") or raw.get("callsign") or raw.get("unit_id") or raw.get("track_id"))
        if not name:
            name = "Unknown Track"
        sidc = self._normalize(raw.get("sidc") or raw.get("symbol_id")) or "00000000000000000000"
        obj = self.data_model.create_object_item(
            name=name,
            category=category,
            hostility=hostility,
            sidc=sidc,
        )
        obj.operational_status = self._operational_status(raw.get("status", "operational"))
        self._detail_by_object[obj.object_item_id] = detail_type
        lat, lon, alt = self._extract_position(raw)
        location = self.data_model.create_location(
            object_item_id=obj.object_item_id,
            lat=lat,
            lon=lon,
            alt=alt,
            bearing=self._to_float(raw.get("heading", raw.get("bearing", 0.0))),
            speed=self._to_float(raw.get("speed", 0.0)),
        )
        return obj, location

    @staticmethod
    def _hostility_to_affiliation(hostility: str) -> str:
        if hostility == "friend":
            return "friendly"
        if hostility == "hostile":
            return "hostile"
        if hostility == "neutral":
            return "neutral"
        return "unknown"

    @staticmethod
    def _status_to_track(op_status: str) -> str:
        if op_status == "degraded":
            return "damaged"
        if op_status == "destroyed":
            return "destroyed"
        return "active"

    def _track_type_from_mip(self, obj: MIPObjectItem) -> str:
        detail = self._detail_by_object.get(obj.object_item_id, "generic")
        if obj.category == "equipment" and detail == "aircraft":
            return "ENEMY_UAV" if obj.hostility_status == "hostile" else "FRIENDLY_UAV"
        if obj.category == "equipment" and detail == "ground_vehicle":
            return "ENEMY_UGV" if obj.hostility_status == "hostile" else "FRIENDLY_UGV"
        if obj.category == "equipment" and detail == "vessel":
            return "ENEMY_SHIP" if obj.hostility_status == "hostile" else "FRIENDLY_SHIP"
        if obj.category == "unit" and detail == "infantry":
            return "ENEMY_INFANTRY" if obj.hostility_status == "hostile" else "FRIENDLY_INFANTRY"
        if obj.category == "facility":
            return "BASE"
        return "UNKNOWN"

    def mip_to_s3m_track(self, obj: MIPObjectItem, loc: MIPLocation) -> dict:
        entity_type = self._track_type_from_mip(obj)
        return {
            "unit_id": obj.object_item_id,
            "name": obj.name,
            "entity_type": entity_type,
            "role": entity_type.lower(),
            "affiliation": self._hostility_to_affiliation(obj.hostility_status),
            "status": self._status_to_track(obj.operational_status),
            "position": [float(loc.latitude), float(loc.longitude), float(loc.altitude)],
            "heading": float(loc.bearing),
            "speed": float(loc.speed),
            "sidc": obj.symbol_id,
            "updated_at": loc.datetime,
        }

    @staticmethod
    def _objective_to_location(unit_id: str, objective: Any) -> Optional[MIPLocation]:
        if isinstance(objective, MIPLocation):
            return objective
        if isinstance(objective, (tuple, list)) and len(objective) >= 2:
            alt = float(objective[2]) if len(objective) > 2 else 0.0
            return MIPLocation(
                object_item_id=str(unit_id),
                latitude=float(objective[0]),
                longitude=float(objective[1]),
                altitude=alt,
                bearing=0.0,
                speed=0.0,
                datetime=datetime.now(timezone.utc).isoformat(),
            )
        if isinstance(objective, dict):
            return MIPLocation(
                object_item_id=str(unit_id),
                latitude=float(objective.get("lat", objective.get("latitude", 0.0))),
                longitude=float(objective.get("lon", objective.get("longitude", 0.0))),
                altitude=float(objective.get("alt", objective.get("altitude", 0.0))),
                bearing=float(objective.get("bearing", objective.get("heading", 0.0))),
                speed=float(objective.get("speed", 0.0)),
                datetime=str(objective.get("datetime", datetime.now(timezone.utc).isoformat())),
            )
        return None

    def s3m_mission_to_mip_task(self, mission: dict) -> MIPActionTask:
        raw = dict(mission or {})
        mission_type = str(raw.get("mission_type", raw.get("type", "PATROL"))).strip().upper()
        action_type = self._MISSION_TYPE_MAP.get(mission_type, mission_type.lower())
        responsible_unit = str(raw.get("unit_id") or raw.get("responsible_unit") or "")
        if not responsible_unit:
            agent_ids = raw.get("agent_ids", [])
            if isinstance(agent_ids, list) and agent_ids:
                responsible_unit = str(agent_ids[0])
        if not responsible_unit:
            responsible_unit = "unknown-unit"
        start_time = str(raw.get("start_time") or self._iso_now())
        end_time = str(raw.get("end_time") or start_time)
        objective = self._objective_to_location(
            responsible_unit,
            raw.get("objective_location") or raw.get("objective") or raw.get("target_location"),
        )
        task = self.data_model.create_action_task(action_type, responsible_unit, start_time, end_time, objective)
        task.order_text = str(raw.get("order_text") or raw.get("description") or "")
        return task

    def mip_task_to_s3m_mission(self, task: MIPActionTask) -> dict:
        mission_type = self._MISSION_REVERSE_MAP.get(task.action_type.lower(), task.action_type.upper())
        objective = None
        waypoints = []
        if task.objective_location is not None:
            objective = {
                "lat": task.objective_location.latitude,
                "lon": task.objective_location.longitude,
                "alt": task.objective_location.altitude,
            }
            waypoints = [[task.objective_location.latitude, task.objective_location.longitude, task.objective_location.altitude]]
        return {
            "mission_id": task.action_id,
            "mission_type": mission_type,
            "unit_id": task.responsible_unit,
            "start_time": task.start_time,
            "end_time": task.end_time,
            "objective_location": objective,
            "waypoints": waypoints,
            "order_text": task.order_text,
        }

    def s3m_orbat_to_mip_oig(self, force: ForceStructure) -> MIPOperationalInfoGroup:
        if not isinstance(force, ForceStructure):
            raise ValueError("force must be ForceStructure")
        owning_unit = force.units[0].unit_id if force.units else force.force_id
        oig = self.data_model.create_oig(category="operations", unit_id=owning_unit)
        for unit in force.units:
            category = "facility" if unit.unit_type in {"facility", "base"} else "unit"
            hostility = "friend" if unit.affiliation.lower() in {"friendly", "allied", "blue"} else "hostile"
            obj = MIPObjectItem(
                object_item_id=unit.unit_id,
                name=unit.name,
                category=category,
                hostility_status=hostility,
                symbol_id=unit.nato_symbol or "00000000000000000000",
                operational_status="operational",
            )
            self.data_model.object_items[obj.object_item_id] = obj
            self._detail_by_object[obj.object_item_id] = unit.unit_type
            oig.items.append(obj.object_item_id)
            if unit.position:
                self.data_model.locations[obj.object_item_id] = MIPLocation(
                    object_item_id=obj.object_item_id,
                    latitude=float(unit.position[0]),
                    longitude=float(unit.position[1]),
                    altitude=0.0,
                    bearing=0.0,
                    speed=0.0,
                    datetime=self._iso_now(),
                )
        self.data_model.oigs[oig.oig_id] = oig
        return oig
