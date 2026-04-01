"""DIS PDU encode/decode factory for Phase 16 interoperability."""

from __future__ import annotations

import struct
import time
from typing import List

from services.interop.models import (
    DISEntityID,
    DISEntityType,
    DISHeader,
    DISLinearVelocity,
    DISOrientation,
    DISPDUType,
    DISWorldCoordinate,
)


class DISPDUFactory:
    """Builds and parses common DIS PDUs using stdlib binary packing."""

    _HEADER_SIZE = struct.calcsize("!BBBBIHH")

    # 132-byte body to keep Entity State total at 144 bytes (12-byte DIS header).
    _ENTITY_STATE_FMT = "!6sBB8s8s12s24s12sIB15s12sI24s"
    _ENTITY_STATE_SIZE = struct.calcsize(_ENTITY_STATE_FMT)

    _FIRE_FMT = "!6s6s6s8s24sI"
    _FIRE_SIZE = struct.calcsize(_FIRE_FMT)

    _DETONATION_FMT = "!6s6s24s8sII"
    _DETONATION_SIZE = struct.calcsize(_DETONATION_FMT)

    _START_RESUME_FMT = "!II"
    _STOP_FREEZE_FMT = "!I"

    _SIGNAL_BASE_FMT = "!6sIHHH"
    _COMMENT_HEADER_FMT = "!H"

    @staticmethod
    def _now_timestamp() -> int:
        return int(time.time())

    @staticmethod
    def _pad_marking(marking: str) -> bytes:
        clipped = (marking or "")[:11]
        return clipped.encode("ascii", errors="ignore").ljust(11, b" ")

    @staticmethod
    def _force_id(value: int) -> int:
        return max(0, min(255, int(value)))

    def _build_header(self, pdu_type: DISPDUType, exercise_id: int, family: int, length: int) -> bytes:
        header = DISHeader(
            protocol_version=7,
            exercise_id=int(exercise_id),
            pdu_type=pdu_type,
            protocol_family=family,
            timestamp=self._now_timestamp(),
            length=length,
            padding=0,
        )
        return header.to_bytes()

    def encode_entity_state(
        self,
        entity_id: DISEntityID,
        entity_type: DISEntityType,
        position: DISWorldCoordinate,
        orientation: DISOrientation,
        velocity: DISLinearVelocity,
        force_id: int,
        exercise_id: int,
        marking: str = "",
    ) -> bytes:
        entity_id_bytes = entity_id.to_bytes()
        entity_type_bytes = entity_type.to_bytes()
        alt_entity_type = DISEntityType(0, 0, 0, 0, 0, 0, 0).to_bytes()
        velocity_bytes = velocity.to_bytes()
        position_bytes = position.to_bytes()
        orientation_bytes = orientation.to_bytes()
        dead_reckoning_parameters = b"\x00" * 15
        marking_bytes = bytes([1]) + self._pad_marking(marking)
        reserved_tail = b"\x00" * 24
        body = struct.pack(
            self._ENTITY_STATE_FMT,
            entity_id_bytes,
            self._force_id(force_id),
            0,  # articulation parameters count
            entity_type_bytes,
            alt_entity_type,
            velocity_bytes,
            position_bytes,
            orientation_bytes,
            0,  # entity appearance
            2,  # dead reckoning algorithm: FPW
            dead_reckoning_parameters,
            marking_bytes,
            0,  # capabilities
            reserved_tail,
        )
        header = self._build_header(
            DISPDUType.ENTITY_STATE,
            exercise_id=exercise_id,
            family=1,
            length=self._HEADER_SIZE + len(body),
        )
        return header + body

    def decode_entity_state(self, data: bytes) -> dict:
        header = DISHeader.from_bytes(data)
        if header.pdu_type != DISPDUType.ENTITY_STATE:
            raise ValueError("Not an Entity State PDU")
        body = data[self._HEADER_SIZE : self._HEADER_SIZE + self._ENTITY_STATE_SIZE]
        if len(body) < self._ENTITY_STATE_SIZE:
            raise ValueError("Entity State PDU body too short")
        (
            entity_id_bytes,
            force_id,
            _articulation_count,
            entity_type_bytes,
            _alt_entity_type,
            velocity_bytes,
            position_bytes,
            orientation_bytes,
            appearance,
            dead_reckoning_algorithm,
            _dr_parameters,
            marking_bytes,
            capabilities,
            _reserved_tail,
        ) = struct.unpack(self._ENTITY_STATE_FMT, body)
        entity_id = DISEntityID.from_bytes(entity_id_bytes)
        entity_type = DISEntityType.from_bytes(entity_type_bytes)
        velocity = DISLinearVelocity.from_bytes(velocity_bytes)
        position = DISWorldCoordinate.from_bytes(position_bytes)
        orientation = DISOrientation.from_bytes(orientation_bytes)
        charset = marking_bytes[0]
        marking = marking_bytes[1:].decode("ascii", errors="ignore").rstrip(" ")
        return {
            "header": {
                "protocol_version": header.protocol_version,
                "exercise_id": header.exercise_id,
                "pdu_type": int(header.pdu_type),
                "protocol_family": header.protocol_family,
                "timestamp": header.timestamp,
                "length": header.length,
            },
            "entity_id": entity_id,
            "entity_type": entity_type,
            "force_id": int(force_id),
            "position": position,
            "orientation": orientation,
            "velocity": velocity,
            "marking": marking,
            "marking_charset": charset,
            "appearance": int(appearance),
            "dead_reckoning_algorithm": int(dead_reckoning_algorithm),
            "capabilities": int(capabilities),
        }

    def encode_fire(
        self,
        firing_entity: DISEntityID,
        target_entity: DISEntityID,
        munition_type: DISEntityType,
        location: DISWorldCoordinate,
        exercise_id: int,
    ) -> bytes:
        body = struct.pack(
            self._FIRE_FMT,
            firing_entity.to_bytes(),
            target_entity.to_bytes(),
            b"\x00" * 6,  # munition id
            munition_type.to_bytes(),
            location.to_bytes(),
            0,  # event id
        )
        header = self._build_header(
            DISPDUType.FIRE, exercise_id=exercise_id, family=2, length=self._HEADER_SIZE + len(body)
        )
        return header + body

    def decode_fire(self, data: bytes) -> dict:
        header = DISHeader.from_bytes(data)
        if header.pdu_type != DISPDUType.FIRE:
            raise ValueError("Not a Fire PDU")
        body = data[self._HEADER_SIZE : self._HEADER_SIZE + self._FIRE_SIZE]
        if len(body) < self._FIRE_SIZE:
            raise ValueError("Fire PDU body too short")
        firing, target, _munition_id, munition, location, event_id = struct.unpack(self._FIRE_FMT, body)
        return {
            "header": {"exercise_id": header.exercise_id, "pdu_type": int(header.pdu_type)},
            "firing_entity": DISEntityID.from_bytes(firing),
            "target_entity": DISEntityID.from_bytes(target),
            "munition_type": DISEntityType.from_bytes(munition),
            "location": DISWorldCoordinate.from_bytes(location),
            "event_id": int(event_id),
        }

    def encode_detonation(
        self,
        firing_entity: DISEntityID,
        target_entity: DISEntityID,
        location: DISWorldCoordinate,
        munition_type: DISEntityType,
        result: int,
        exercise_id: int,
    ) -> bytes:
        body = struct.pack(
            self._DETONATION_FMT,
            firing_entity.to_bytes(),
            target_entity.to_bytes(),
            location.to_bytes(),
            munition_type.to_bytes(),
            int(result) & 0xFFFF,
            0,  # event id
        )
        header = self._build_header(
            DISPDUType.DETONATION,
            exercise_id=exercise_id,
            family=2,
            length=self._HEADER_SIZE + len(body),
        )
        return header + body

    def decode_detonation(self, data: bytes) -> dict:
        header = DISHeader.from_bytes(data)
        if header.pdu_type != DISPDUType.DETONATION:
            raise ValueError("Not a Detonation PDU")
        body = data[self._HEADER_SIZE : self._HEADER_SIZE + self._DETONATION_SIZE]
        if len(body) < self._DETONATION_SIZE:
            raise ValueError("Detonation PDU body too short")
        firing, target, location, munition, result, event_id = struct.unpack(self._DETONATION_FMT, body)
        return {
            "header": {"exercise_id": header.exercise_id, "pdu_type": int(header.pdu_type)},
            "firing_entity": DISEntityID.from_bytes(firing),
            "target_entity": DISEntityID.from_bytes(target),
            "location": DISWorldCoordinate.from_bytes(location),
            "munition_type": DISEntityType.from_bytes(munition),
            "result": int(result),
            "event_id": int(event_id),
        }

    def encode_start_resume(self, exercise_id: int, real_world_time: int, sim_time: int) -> bytes:
        body = struct.pack(self._START_RESUME_FMT, int(real_world_time), int(sim_time))
        header = self._build_header(
            DISPDUType.START_RESUME,
            exercise_id=exercise_id,
            family=5,
            length=self._HEADER_SIZE + len(body),
        )
        return header + body

    def encode_stop_freeze(self, exercise_id: int, reason: int) -> bytes:
        body = struct.pack(self._STOP_FREEZE_FMT, int(reason))
        header = self._build_header(
            DISPDUType.STOP_FREEZE,
            exercise_id=exercise_id,
            family=5,
            length=self._HEADER_SIZE + len(body),
        )
        return header + body

    def encode_signal(
        self,
        entity_id: DISEntityID,
        radio_id: int,
        encoding: int,
        data: bytes,
        exercise_id: int,
    ) -> bytes:
        payload = bytes(data)
        base = struct.pack(
            self._SIGNAL_BASE_FMT,
            entity_id.to_bytes(),
            int(radio_id) & 0xFFFFFFFF,
            int(encoding) & 0xFFFF,
            len(payload) & 0xFFFF,
            len(payload) * 8,
        )
        body = base + payload
        header = self._build_header(
            DISPDUType.SIGNAL, exercise_id=exercise_id, family=4, length=self._HEADER_SIZE + len(body)
        )
        return header + body

    def decode_signal(self, data: bytes) -> dict:
        header = DISHeader.from_bytes(data)
        if header.pdu_type != DISPDUType.SIGNAL:
            raise ValueError("Not a Signal PDU")
        base_size = struct.calcsize(self._SIGNAL_BASE_FMT)
        body = data[self._HEADER_SIZE :]
        if len(body) < base_size:
            raise ValueError("Signal PDU body too short")
        entity_bytes, radio_id, encoding, data_len, sample_count = struct.unpack(
            self._SIGNAL_BASE_FMT, body[:base_size]
        )
        signal_data = body[base_size : base_size + data_len]
        return {
            "header": {"exercise_id": header.exercise_id, "pdu_type": int(header.pdu_type)},
            "entity_id": DISEntityID.from_bytes(entity_bytes),
            "radio_id": int(radio_id),
            "encoding": int(encoding),
            "sample_count": int(sample_count),
            "data": signal_data,
        }

    def encode_comment(self, exercise_id: int, data_records: List[dict]) -> bytes:
        records: List[bytes] = []
        for record in data_records:
            key = str(record.get("key", "text"))
            value = str(record.get("value", ""))
            payload = f"{key}={value}".encode("utf-8")
            records.append(struct.pack("!H", len(payload)) + payload)
        body = struct.pack(self._COMMENT_HEADER_FMT, len(records)) + b"".join(records)
        header = self._build_header(
            DISPDUType.COMMENT, exercise_id=exercise_id, family=6, length=self._HEADER_SIZE + len(body)
        )
        return header + body

    def identify_pdu_type(self, data: bytes) -> DISPDUType:
        header = DISHeader.from_bytes(data)
        return header.pdu_type

    def decode_any(self, data: bytes) -> dict:
        pdu_type = self.identify_pdu_type(data)
        if pdu_type == DISPDUType.ENTITY_STATE:
            return {"pdu_type": int(pdu_type), "data": self.decode_entity_state(data)}
        if pdu_type == DISPDUType.FIRE:
            return {"pdu_type": int(pdu_type), "data": self.decode_fire(data)}
        if pdu_type == DISPDUType.DETONATION:
            return {"pdu_type": int(pdu_type), "data": self.decode_detonation(data)}
        if pdu_type == DISPDUType.SIGNAL:
            return {"pdu_type": int(pdu_type), "data": self.decode_signal(data)}
        return {"pdu_type": int(pdu_type), "data": {"raw_hex": data.hex()}}
