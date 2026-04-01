"""Data models for S3M Phase 16 expanded interoperability stack."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
import math
import struct
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
from xml.etree import ElementTree as ET


class DISPDUType(IntEnum):
    ENTITY_STATE = 1
    FIRE = 2
    DETONATION = 3
    COLLISION = 4
    SERVICE_REQUEST = 5
    RESUPPLY_OFFER = 6
    REPAIR_COMPLETE = 9
    COLLISION_ELASTIC = 10
    CREATE_ENTITY = 11
    REMOVE_ENTITY = 12
    START_RESUME = 13
    STOP_FREEZE = 14
    ACKNOWLEDGE = 15
    ACTION_REQUEST = 16
    SET_DATA = 19
    DATA = 20
    COMMENT = 22
    ELECTROMAGNETIC_EMISSION = 23
    TRANSMITTER = 25
    SIGNAL = 26
    RECEIVER = 27


@dataclass
class DISHeader:
    protocol_version: int = 7
    exercise_id: int = 1
    pdu_type: DISPDUType = DISPDUType.ENTITY_STATE
    protocol_family: int = 1
    timestamp: int = 0
    length: int = 0
    padding: int = 0

    _FORMAT = "!BBBBIHH"

    def to_bytes(self) -> bytes:
        return struct.pack(
            self._FORMAT,
            int(self.protocol_version) & 0xFF,
            int(self.exercise_id) & 0xFF,
            int(self.pdu_type) & 0xFF,
            int(self.protocol_family) & 0xFF,
            int(self.timestamp) & 0xFFFFFFFF,
            int(self.length) & 0xFFFF,
            int(self.padding) & 0xFFFF,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "DISHeader":
        size = struct.calcsize(cls._FORMAT)
        if len(data) < size:
            raise ValueError("DIS header too short")
        pver, ex, pdu, fam, ts, length, pad = struct.unpack(cls._FORMAT, data[:size])
        return cls(
            protocol_version=pver,
            exercise_id=ex,
            pdu_type=DISPDUType(pdu),
            protocol_family=fam,
            timestamp=ts,
            length=length,
            padding=pad,
        )


@dataclass(frozen=True)
class DISEntityID:
    site_id: int
    application_id: int
    entity_id: int

    _FORMAT = "!HHH"

    def to_bytes(self) -> bytes:
        return struct.pack(
            self._FORMAT,
            int(self.site_id) & 0xFFFF,
            int(self.application_id) & 0xFFFF,
            int(self.entity_id) & 0xFFFF,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "DISEntityID":
        size = struct.calcsize(cls._FORMAT)
        if len(data) < size:
            raise ValueError("DISEntityID byte payload too short")
        site, app, ent = struct.unpack(cls._FORMAT, data[:size])
        return cls(site_id=site, application_id=app, entity_id=ent)

    def to_tuple(self) -> tuple:
        return (self.site_id, self.application_id, self.entity_id)


def _lla_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> tuple[float, float, float]:
    a = 6378137.0
    f = 1.0 / 298.257223563
    e_sq = f * (2.0 - f)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)
    n = a / math.sqrt(1.0 - e_sq * sin_lat * sin_lat)
    x = (n + alt_m) * cos_lat * cos_lon
    y = (n + alt_m) * cos_lat * sin_lon
    z = (n * (1.0 - e_sq) + alt_m) * sin_lat
    return (x, y, z)


def _ecef_to_lla(x: float, y: float, z: float) -> tuple[float, float, float]:
    a = 6378137.0
    b = 6356752.314245
    f = 1.0 / 298.257223563
    e_sq = f * (2.0 - f)
    ep_sq = (a * a - b * b) / (b * b)
    lon = math.atan2(y, x)
    p = math.sqrt(x * x + y * y)
    if p == 0.0:
        lat = math.copysign(math.pi / 2.0, z)
        h = abs(z) - b
        return (math.degrees(lat), math.degrees(lon), h)
    theta = math.atan2(z * a, p * b)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    lat = math.atan2(z + ep_sq * b * sin_theta**3, p - e_sq * a * cos_theta**3)
    for _ in range(3):
        sin_lat = math.sin(lat)
        n = a / math.sqrt(1.0 - e_sq * sin_lat * sin_lat)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1.0 - e_sq * (n / (n + h))))
    sin_lat = math.sin(lat)
    n = a / math.sqrt(1.0 - e_sq * sin_lat * sin_lat)
    h = p / math.cos(lat) - n
    return (math.degrees(lat), math.degrees(lon), h)


@dataclass
class DISWorldCoordinate:
    x: float
    y: float
    z: float

    _FORMAT = "!ddd"

    def to_bytes(self) -> bytes:
        return struct.pack(self._FORMAT, float(self.x), float(self.y), float(self.z))

    @classmethod
    def from_bytes(cls, data: bytes) -> "DISWorldCoordinate":
        size = struct.calcsize(cls._FORMAT)
        if len(data) < size:
            raise ValueError("DISWorldCoordinate byte payload too short")
        x, y, z = struct.unpack(cls._FORMAT, data[:size])
        return cls(x=x, y=y, z=z)

    def to_lat_lon_alt(self) -> tuple:
        return _ecef_to_lla(self.x, self.y, self.z)

    @classmethod
    def from_lat_lon_alt(cls, lat: float, lon: float, alt: float) -> "DISWorldCoordinate":
        x, y, z = _lla_to_ecef(lat, lon, alt)
        return cls(x=x, y=y, z=z)


@dataclass
class DISOrientation:
    psi: float
    theta: float
    phi: float

    _FORMAT = "!fff"

    def to_bytes(self) -> bytes:
        return struct.pack(self._FORMAT, float(self.psi), float(self.theta), float(self.phi))

    @classmethod
    def from_bytes(cls, data: bytes) -> "DISOrientation":
        size = struct.calcsize(cls._FORMAT)
        if len(data) < size:
            raise ValueError("DISOrientation byte payload too short")
        psi, theta, phi = struct.unpack(cls._FORMAT, data[:size])
        return cls(psi=psi, theta=theta, phi=phi)


@dataclass
class DISLinearVelocity:
    x: float
    y: float
    z: float

    _FORMAT = "!fff"

    def to_bytes(self) -> bytes:
        return struct.pack(self._FORMAT, float(self.x), float(self.y), float(self.z))

    @classmethod
    def from_bytes(cls, data: bytes) -> "DISLinearVelocity":
        size = struct.calcsize(cls._FORMAT)
        if len(data) < size:
            raise ValueError("DISLinearVelocity byte payload too short")
        x, y, z = struct.unpack(cls._FORMAT, data[:size])
        return cls(x=x, y=y, z=z)


@dataclass
class DISEntityType:
    kind: int
    domain: int
    country: int
    category: int
    subcategory: int
    specific: int
    extra: int

    _FORMAT = "!BBHBBBB"

    def to_bytes(self) -> bytes:
        return struct.pack(
            self._FORMAT,
            int(self.kind) & 0xFF,
            int(self.domain) & 0xFF,
            int(self.country) & 0xFFFF,
            int(self.category) & 0xFF,
            int(self.subcategory) & 0xFF,
            int(self.specific) & 0xFF,
            int(self.extra) & 0xFF,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "DISEntityType":
        size = struct.calcsize(cls._FORMAT)
        if len(data) < size:
            raise ValueError("DISEntityType byte payload too short")
        kind, domain, country, category, subcategory, specific, extra = struct.unpack(
            cls._FORMAT, data[:size]
        )
        return cls(kind, domain, country, category, subcategory, specific, extra)

    def is_friendly(self, country_code: int = 178) -> bool:
        return int(self.country) == int(country_code)


@dataclass
class ExerciseSession:
    exercise_id: int
    exercise_name: str
    description: str
    start_time: datetime
    end_time: Optional[datetime]
    participating_nations: List[dict]
    status: str
    dis_config: dict
    c2sim_config: dict
    entities_count: int = 0
    events_count: int = 0

    def to_dict(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "description": self.description,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "participating_nations": list(self.participating_nations),
            "status": self.status,
            "dis_config": dict(self.dis_config),
            "c2sim_config": dict(self.c2sim_config),
            "entities_count": int(self.entities_count),
            "events_count": int(self.events_count),
        }

    def is_active(self) -> bool:
        return self.status == "active" and self.end_time is None

    def duration_seconds(self) -> Optional[float]:
        if self.end_time is not None:
            return max(0.0, (self.end_time - self.start_time).total_seconds())
        if self.status in {"active", "paused"}:
            return max(0.0, (datetime.now(timezone.utc) - self.start_time).total_seconds())
        return None


@dataclass
class ORBATUnit:
    unit_id: str
    name: str
    designation: str
    echelon: str
    unit_type: str
    affiliation: str
    parent_unit_id: Optional[str]
    subordinate_ids: List[str]
    country_code: int
    nato_symbol: str
    strength: int
    equipment: List[dict]
    position: Optional[tuple]
    commander: Optional[str]

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "designation": self.designation,
            "echelon": self.echelon,
            "unit_type": self.unit_type,
            "affiliation": self.affiliation,
            "parent_unit_id": self.parent_unit_id,
            "subordinate_ids": list(self.subordinate_ids),
            "country_code": int(self.country_code),
            "nato_symbol": self.nato_symbol,
            "strength": int(self.strength),
            "equipment": list(self.equipment),
            "position": tuple(self.position) if self.position else None,
            "commander": self.commander,
        }

    def to_msdl(self) -> str:
        unit = ET.Element("Unit")
        ET.SubElement(unit, "UnitID").text = self.unit_id
        ET.SubElement(unit, "Name").text = self.name
        ET.SubElement(unit, "Designation").text = self.designation
        ET.SubElement(unit, "Echelon").text = self.echelon
        ET.SubElement(unit, "UnitType").text = self.unit_type
        ET.SubElement(unit, "Affiliation").text = self.affiliation
        ET.SubElement(unit, "CountryCode").text = str(self.country_code)
        ET.SubElement(unit, "NATOSymbol").text = self.nato_symbol
        ET.SubElement(unit, "Strength").text = str(self.strength)
        if self.parent_unit_id:
            ET.SubElement(unit, "ParentUnitID").text = self.parent_unit_id
        if self.commander:
            ET.SubElement(unit, "Commander").text = self.commander
        if self.position:
            pos = ET.SubElement(unit, "Position")
            ET.SubElement(pos, "Latitude").text = str(self.position[0])
            ET.SubElement(pos, "Longitude").text = str(self.position[1])
        subordinates = ET.SubElement(unit, "SubordinateUnitIDs")
        for sub in self.subordinate_ids:
            ET.SubElement(subordinates, "UnitID").text = sub
        equipment_node = ET.SubElement(unit, "Equipment")
        for item in self.equipment:
            eq = ET.SubElement(equipment_node, "Item")
            for key, value in item.items():
                ET.SubElement(eq, str(key)).text = str(value)
        return ET.tostring(unit, encoding="unicode")

    def get_nato_symbol_id(self) -> str:
        if self.nato_symbol:
            return self.nato_symbol
        return f"{self.affiliation[:1].upper()}-{self.unit_type[:3].upper()}-{self.echelon[:3].upper()}"


@dataclass
class ForceStructure:
    force_id: str
    force_name: str
    affiliation: str
    units: List[ORBATUnit]
    country_code: int

    def to_dict(self) -> dict:
        return {
            "force_id": self.force_id,
            "force_name": self.force_name,
            "affiliation": self.affiliation,
            "country_code": int(self.country_code),
            "units": [u.to_dict() for u in self.units],
        }

    def get_unit(self, unit_id) -> Optional[ORBATUnit]:
        for unit in self.units:
            if unit.unit_id == unit_id:
                return unit
        return None

    def total_strength(self) -> int:
        return sum(int(unit.strength) for unit in self.units)

    def unit_count(self) -> int:
        return len(self.units)

    def to_msdl(self) -> str:
        force = ET.Element("ForceSide")
        ET.SubElement(force, "ForceID").text = self.force_id
        ET.SubElement(force, "ForceName").text = self.force_name
        ET.SubElement(force, "Affiliation").text = self.affiliation
        ET.SubElement(force, "CountryCode").text = str(self.country_code)
        units_node = ET.SubElement(force, "Units")
        for unit in self.units:
            units_node.append(ET.fromstring(unit.to_msdl()))
        return ET.tostring(force, encoding="unicode")


@dataclass
class MSDLScenario:
    scenario_id: str
    name: str
    description: str
    forces: List[ForceStructure]
    environment: dict
    overlay: dict
    version: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "forces": [force.to_dict() for force in self.forces],
            "environment": dict(self.environment),
            "overlay": dict(self.overlay),
            "version": self.version,
            "created_at": self.created_at.isoformat(),
        }

    def to_xml(self) -> str:
        root = ET.Element("MilitaryScenario")
        ET.SubElement(root, "ScenarioID").text = self.scenario_id
        ET.SubElement(root, "Name").text = self.name
        ET.SubElement(root, "Description").text = self.description
        ET.SubElement(root, "Version").text = self.version
        ET.SubElement(root, "CreatedAt").text = self.created_at.isoformat()

        force_sides = ET.SubElement(root, "ForceSides")
        for force in self.forces:
            force_sides.append(ET.fromstring(force.to_msdl()))

        env = ET.SubElement(root, "Environment")
        for key, value in self.environment.items():
            ET.SubElement(env, str(key)).text = str(value)

        overlay = ET.SubElement(root, "Overlay")
        for key, value in self.overlay.items():
            item = ET.SubElement(overlay, str(key))
            if isinstance(value, list):
                for entry in value:
                    ET.SubElement(item, "Item").text = str(entry)
            elif isinstance(value, dict):
                for d_key, d_val in value.items():
                    ET.SubElement(item, str(d_key)).text = str(d_val)
            else:
                item.text = str(value)
        return ET.tostring(root, encoding="unicode")

    def total_units(self) -> int:
        return sum(force.unit_count() for force in self.forces)


def build_orbat_unit(
    name: str,
    designation: str,
    echelon: str,
    unit_type: str,
    affiliation: str,
    country_code: int = 178,
    parent_unit_id: Optional[str] = None,
    nato_symbol: str = "",
    strength: int = 0,
    equipment: Optional[List[dict]] = None,
    position: Optional[Tuple[float, float]] = None,
    commander: Optional[str] = None,
) -> ORBATUnit:
    return ORBATUnit(
        unit_id=f"unit-{uuid4().hex[:10]}",
        name=name,
        designation=designation,
        echelon=echelon,
        unit_type=unit_type,
        affiliation=affiliation,
        parent_unit_id=parent_unit_id,
        subordinate_ids=[],
        country_code=country_code,
        nato_symbol=nato_symbol,
        strength=strength,
        equipment=equipment or [],
        position=position,
        commander=commander,
    )
