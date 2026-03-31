"""DIS protocol adapter for IEEE-1278.1 interoperability."""

from __future__ import annotations

import socket
import struct
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from src.simulation.models import EntityType
except Exception:  # pragma: no cover - defensive import fallback
    EntityType = None  # type: ignore[assignment]


DIS_ENTITY_MAP: Dict[str, Dict[str, int]] = {
    "FRIENDLY_UAV": {"kind": 1, "domain": 2, "country": 178, "category": 1, "subcategory": 0},
    "FRIENDLY_UGV": {"kind": 1, "domain": 1, "country": 178, "category": 1, "subcategory": 0},
    "FRIENDLY_SHIP": {"kind": 1, "domain": 3, "country": 178, "category": 1, "subcategory": 0},
    "ENEMY_UAV": {"kind": 1, "domain": 2, "country": 0, "category": 1, "subcategory": 0},
    "ENEMY_UGV": {"kind": 1, "domain": 1, "country": 0, "category": 1, "subcategory": 0},
    "ENEMY_SHIP": {"kind": 1, "domain": 3, "country": 0, "category": 1, "subcategory": 0},
    "ENEMY_INFANTRY": {"kind": 3, "domain": 1, "country": 0, "category": 1, "subcategory": 0},
    "CIVILIAN": {"kind": 3, "domain": 1, "country": 0, "category": 0, "subcategory": 0},
    "OBSTACLE": {"kind": 2, "domain": 1, "country": 0, "category": 0, "subcategory": 0},
    "WAYPOINT": {"kind": 9, "domain": 0, "country": 0, "category": 0, "subcategory": 0},
    "BASE": {"kind": 1, "domain": 1, "country": 178, "category": 2, "subcategory": 0},
    "UNKNOWN": {"kind": 0, "domain": 0, "country": 0, "category": 0, "subcategory": 0},
}

_REVERSE_ENTITY_MAP: Dict[tuple[int, int, int, int, int], str] = {
    (
        payload["kind"],
        payload["domain"],
        payload["country"],
        payload["category"],
        payload.get("subcategory", 0),
    ): key
    for key, payload in DIS_ENTITY_MAP.items()
}


def _to_force_id(allegiance: str) -> int:
    text = (allegiance or "").strip().lower()
    if text in {"friendly", "blue", "allied"}:
        return 1
    if text in {"enemy", "opposing", "red"}:
        return 2
    return 3


def _from_force_id(force_id: int) -> str:
    return {1: "friendly", 2: "enemy", 3: "neutral"}.get(force_id, "neutral")


class DISAdapter:
    """Encodes/decodes essential DIS PDUs for coalition simulation exchange."""

    def __init__(
        self,
        exercise_id: int = 1,
        site_id: int = 1,
        app_id: int = 1,
        broadcast_address: str = "255.255.255.255",
        port: int = 3000,
    ):
        self.exercise_id = int(exercise_id)
        self.site_id = int(site_id)
        self.app_id = int(app_id)
        self.broadcast_address = broadcast_address
        self.port = int(port)
        self.socket: Optional[socket.socket] = None
        self.connected = False

    def connect(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("0.0.0.0", self.port))
            sock.setblocking(False)
            self.socket = sock
            self.connected = True
            return True
        except OSError:
            self.socket = None
            self.connected = False
            return False

    def disconnect(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
        self.socket = None
        self.connected = False

    def encode_entity_state(self, entity: Dict[str, Any]) -> bytes:
        # Tactical interoperability note: compact, deterministic binary layout allows
        # low-latency entity state exchange across constrained coalition links.
        entity_id = int(entity.get("entity_id", 0))
        force_id = _to_force_id(str(entity.get("allegiance", "neutral")))
        entity_type_name = str(entity.get("entity_type", "UNKNOWN"))
        entity_type = DIS_ENTITY_MAP.get(entity_type_name, DIS_ENTITY_MAP["UNKNOWN"])
        location = entity.get("location", entity.get("position", {}))
        orientation = entity.get("orientation", {})
        velocity = entity.get("velocity", {})

        loc_x = float(location.get("x", 0.0))
        loc_y = float(location.get("y", 0.0))
        loc_z = float(location.get("z", 0.0))
        psi = float(orientation.get("psi", 0.0))
        theta = float(orientation.get("theta", 0.0))
        phi = float(orientation.get("phi", 0.0))
        vel_x = float(velocity.get("x", 0.0))
        vel_y = float(velocity.get("y", 0.0))
        vel_z = float(velocity.get("z", 0.0))

        timestamp = int(time.time())
        header_fmt = "!BBBBIHH"
        body_fmt = "!HHHBBHBBBBdddffffff"
        total_length = struct.calcsize(header_fmt) + struct.calcsize(body_fmt)

        header = struct.pack(
            header_fmt,
            7,  # protocol version DIS 7
            self.exercise_id & 0xFF,
            1,  # entity state PDU
            1,  # protocol family
            timestamp,
            total_length,
            0,
        )
        body = struct.pack(
            body_fmt,
            self.site_id & 0xFFFF,
            self.app_id & 0xFFFF,
            entity_id & 0xFFFF,
            force_id & 0xFF,
            entity_type["kind"] & 0xFF,
            entity_type["country"] & 0xFFFF,
            entity_type["domain"] & 0xFF,
            entity_type["category"] & 0xFF,
            entity_type.get("subcategory", 0) & 0xFF,
            0,
            loc_x,
            loc_y,
            loc_z,
            psi,
            theta,
            phi,
            vel_x,
            vel_y,
            vel_z,
        )
        return header + body

    def decode_entity_state(self, data: bytes) -> Dict[str, Any]:
        header_fmt = "!BBBBIHH"
        body_fmt = "!HHHBBHBBBBdddffffff"
        header_size = struct.calcsize(header_fmt)
        body_size = struct.calcsize(body_fmt)
        if len(data) < header_size + body_size:
            raise ValueError("DIS entity state PDU too short")

        p_version, exercise_id, pdu_type, family, timestamp, length, _pad = struct.unpack(
            header_fmt, data[:header_size]
        )
        if pdu_type != 1:
            raise ValueError(f"Unsupported PDU type: {pdu_type}")
        (
            site_id,
            app_id,
            entity_id,
            force_id,
            kind,
            country,
            domain,
            category,
            subcategory,
            _reserved,
            loc_x,
            loc_y,
            loc_z,
            psi,
            theta,
            phi,
            vel_x,
            vel_y,
            vel_z,
        ) = struct.unpack(body_fmt, data[header_size : header_size + body_size])
        entity_type_key = _REVERSE_ENTITY_MAP.get((kind, domain, country, category, subcategory), "UNKNOWN")
        return {
            "entity_id": entity_id,
            "force_id": force_id,
            "allegiance": _from_force_id(force_id),
            "entity_type": entity_type_key,
            "location": {"x": loc_x, "y": loc_y, "z": loc_z},
            "orientation": {"psi": psi, "theta": theta, "phi": phi},
            "velocity": {"x": vel_x, "y": vel_y, "z": vel_z},
            "timestamp": timestamp,
            "header": {
                "protocol_version": p_version,
                "exercise_id": exercise_id,
                "pdu_type": pdu_type,
                "protocol_family": family,
                "length": length,
                "site_id": site_id,
                "app_id": app_id,
            },
        }

    def send_entity_update(self, entity: Dict[str, Any]) -> bool:
        if not self.socket:
            return False
        try:
            payload = self.encode_entity_state(entity)
            self.socket.sendto(payload, (self.broadcast_address, self.port))
            return True
        except OSError:
            return False

    def receive(self, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        if not self.socket:
            return None
        self.socket.settimeout(timeout)
        try:
            data, _addr = self.socket.recvfrom(4096)
        except (BlockingIOError, TimeoutError, OSError):
            return None
        try:
            return self.decode_entity_state(data)
        except Exception:
            return None

    def sim_entity_to_dis(self, sim_entity: Any) -> Dict[str, Any]:
        entity_type_value = "UNKNOWN"
        if hasattr(sim_entity, "entity_type"):
            raw_type = getattr(sim_entity, "entity_type")
            entity_type_value = getattr(raw_type, "value", str(raw_type))
        allegiance = "friendly" if entity_type_value.startswith("FRIENDLY_") else "enemy"
        if entity_type_value in {"CIVILIAN", "UNKNOWN", "OBSTACLE", "WAYPOINT", "BASE"}:
            allegiance = "neutral"
        pos = getattr(sim_entity, "position", (0.0, 0.0, 0.0))
        vel = getattr(sim_entity, "velocity", (0.0, 0.0, 0.0))
        heading = float(getattr(sim_entity, "heading", 0.0))
        raw_entity_id = getattr(sim_entity, "entity_id", 0)
        if isinstance(raw_entity_id, str):
            try:
                entity_id = int(raw_entity_id)
            except ValueError:
                entity_id = sum(ord(ch) for ch in raw_entity_id) % 65535
        else:
            entity_id = int(raw_entity_id)
        return {
            "entity_id": entity_id,
            "allegiance": allegiance,
            "entity_type": entity_type_value,
            "location": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
            "orientation": {"psi": heading, "theta": 0.0, "phi": 0.0},
            "velocity": {"x": float(vel[0]), "y": float(vel[1]), "z": float(vel[2])},
        }

    def dis_to_sim_entity(self, dis_entity: Dict[str, Any]) -> Dict[str, Any]:
        location = dis_entity.get("location", {})
        velocity = dis_entity.get("velocity", {})
        orientation = dis_entity.get("orientation", {})
        entity_type_name = dis_entity.get("entity_type", "UNKNOWN")
        return {
            "entity_id": f"dis-{dis_entity.get('entity_id', 0)}",
            "entity_type": entity_type_name,
            "position": (
                float(location.get("x", 0.0)),
                float(location.get("y", 0.0)),
                float(location.get("z", 0.0)),
            ),
            "velocity": (
                float(velocity.get("x", 0.0)),
                float(velocity.get("y", 0.0)),
                float(velocity.get("z", 0.0)),
            ),
            "heading": float(orientation.get("psi", 0.0)),
            "health": 1.0,
            "active": True,
            "metadata": {
                "protocol": "DIS",
                "allegiance": dis_entity.get("allegiance", _from_force_id(dis_entity.get("force_id", 3))),
                "received_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def encode_fire_pdu(
        self,
        shooter_id: int,
        target_id: int,
        munition_type: str,
        location: Dict[str, float],
    ) -> bytes:
        header_fmt = "!BBBBIHH"
        body_fmt = "!HHHHHHddd"
        total_length = struct.calcsize(header_fmt) + struct.calcsize(body_fmt)
        header = struct.pack(
            header_fmt,
            7,
            self.exercise_id & 0xFF,
            2,
            2,
            int(time.time()),
            total_length,
            0,
        )
        munition_code = sum(munition_type.encode("utf-8")) & 0xFFFF
        body = struct.pack(
            body_fmt,
            self.site_id & 0xFFFF,
            self.app_id & 0xFFFF,
            shooter_id & 0xFFFF,
            self.site_id & 0xFFFF,
            self.app_id & 0xFFFF,
            target_id & 0xFFFF,
            float(location.get("x", 0.0)),
            float(location.get("y", 0.0)),
            float(location.get("z", 0.0)),
        )
        return header + body + struct.pack("!H", munition_code)

    def encode_detonation_pdu(
        self,
        target_id: int,
        location: Dict[str, float],
        result: str,
    ) -> bytes:
        header_fmt = "!BBBBIHH"
        body_fmt = "!HHHdddH"
        total_length = struct.calcsize(header_fmt) + struct.calcsize(body_fmt)
        header = struct.pack(
            header_fmt,
            7,
            self.exercise_id & 0xFF,
            3,
            2,
            int(time.time()),
            total_length,
            0,
        )
        result_code = sum(result.encode("utf-8")) & 0xFFFF
        body = struct.pack(
            body_fmt,
            self.site_id & 0xFFFF,
            self.app_id & 0xFFFF,
            target_id & 0xFFFF,
            float(location.get("x", 0.0)),
            float(location.get("y", 0.0)),
            float(location.get("z", 0.0)),
            result_code,
        )
        return header + body
