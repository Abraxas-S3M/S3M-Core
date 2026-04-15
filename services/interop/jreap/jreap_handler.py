"""Binary JREAP-C parsing helpers for Link 16 J-series payload ingest."""

from __future__ import annotations

from datetime import datetime, timezone
import struct
import time
from typing import Dict, List


class JREAPHandler:
    """Encodes/decodes JREAP-C headers and selected tactical J-series payloads."""

    HEADER_FORMAT = "!HHIQI"
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

    _TRACK_RECORD_SIZE = 13
    _EMERGENCY_RECORD_SIZE = 9

    _SERIES_CODE_TO_TYPE = {
        0x22: "J2.2",
        0x32: "J3.2",
        0x35: "J3.5",
        0xD2: "J13.2",
    }

    _TYPE_TO_DOMAIN = {
        "J2.2": "air",
        "J3.2": "surface",
        "J3.5": "land",
        "J13.2": "air",
    }

    def __init__(self, config: dict | None = None):
        cfg = config or {}
        self.protocol_version = int(cfg.get("protocol_version", 1))
        self.supported_j_series = list(cfg.get("supported_j_series", ["J2.2", "J3.2", "J3.5", "J13.2"]))
        self._sequence_number = int(cfg.get("initial_sequence", 0)) & 0xFFFFFFFF

    def parse_jreap_header(self, data: bytes) -> dict:
        """Parse the fixed 20-byte JREAP-C header."""
        if len(data) < self.HEADER_SIZE:
            raise ValueError("JREAP-C packet too short for 20-byte header")
        version, message_type, sequence, timestamp_usec, payload_length = struct.unpack(
            self.HEADER_FORMAT, data[: self.HEADER_SIZE]
        )
        return {
            "protocol_version": int(version),
            "message_type": int(message_type),
            "sequence_number": int(sequence),
            "timestamp_us": int(timestamp_usec),
            "payload_length": int(payload_length),
        }

    def parse_j_series(self, payload: bytes, msg_type: str) -> List[dict]:
        """Decode J-series records from JREAP payload bytes."""
        normalized = str(msg_type or "").strip().upper()
        if normalized in {"", "AUTO", "MIXED"}:
            return self._parse_mixed_records(payload)
        if normalized not in {"J2.2", "J3.2", "J3.5", "J13.2"}:
            return []
        if normalized == "J13.2":
            return self._parse_emergency_records(payload)
        return self._parse_track_records(payload, normalized)

    def encode_jreap_header(self, msg_type: int, payload: bytes) -> bytes:
        """Build JREAP-C header for outbound transport framing."""
        self._sequence_number = (self._sequence_number + 1) & 0xFFFFFFFF
        timestamp_usec = int(time.time() * 1_000_000)
        return struct.pack(
            self.HEADER_FORMAT,
            int(self.protocol_version) & 0xFFFF,
            int(msg_type) & 0xFFFF,
            self._sequence_number,
            timestamp_usec,
            len(payload) & 0xFFFFFFFF,
        )

    def encode_j2_2(self, track: dict) -> bytes:
        """Phase 2 transmit placeholder for J2.2 generation."""
        _ = track
        return b""

    @staticmethod
    def _decode_lat_23bit(raw: int) -> float:
        return (float(raw) / float(1 << 23)) * 180.0 - 90.0

    @staticmethod
    def _decode_lon_24bit(raw: int) -> float:
        return (float(raw) / float(1 << 24)) * 360.0 - 180.0

    def _parse_mixed_records(self, payload: bytes) -> List[dict]:
        rows: List[dict] = []
        offset = 0
        while offset + 2 <= len(payload):
            code, length = struct.unpack("!BB", payload[offset : offset + 2])
            offset += 2
            if length <= 0 or offset + length > len(payload):
                break
            message_payload = struct.unpack(f"!{length}s", payload[offset : offset + length])[0]
            offset += length
            message_type = self._SERIES_CODE_TO_TYPE.get(code)
            if message_type is None:
                continue
            rows.extend(self.parse_j_series(message_payload, message_type))
        return rows

    def _parse_track_records(self, payload: bytes, j_series: str) -> List[dict]:
        if len(payload) < self._TRACK_RECORD_SIZE:
            return []
        rows: List[dict] = []
        domain = self._TYPE_TO_DOMAIN.get(j_series, "air")
        record_count = len(payload) // self._TRACK_RECORD_SIZE
        for idx in range(record_count):
            start = idx * self._TRACK_RECORD_SIZE
            end = start + self._TRACK_RECORD_SIZE
            record = struct.unpack(f"!{self._TRACK_RECORD_SIZE}s", payload[start:end])[0]
            rows.append(self._decode_track_record(record=record, j_series=j_series, domain=domain))
        return rows

    def _parse_emergency_records(self, payload: bytes) -> List[dict]:
        if len(payload) < self._EMERGENCY_RECORD_SIZE:
            return []
        rows: List[dict] = []
        record_count = len(payload) // self._EMERGENCY_RECORD_SIZE
        for idx in range(record_count):
            start = idx * self._EMERGENCY_RECORD_SIZE
            end = start + self._EMERGENCY_RECORD_SIZE
            record = struct.unpack(f"!{self._EMERGENCY_RECORD_SIZE}s", payload[start:end])[0]
            rows.append(self._decode_j13_2_record(record=record, record_index=idx))
        return rows

    def _decode_track_record(self, record: bytes, j_series: str, domain: str) -> Dict[str, object]:
        word = int.from_bytes(record, byteorder="big", signed=False)
        # Tactical interoperability note: these bit widths follow an open-source
        # baseline profile and may need adjustment once validated against the
        # exact coalition Link 16/JREAP implementation reference.
        track_number = (word >> 91) & 0x1FFF
        raw_lat = (word >> 68) & ((1 << 23) - 1)
        raw_lon = (word >> 44) & ((1 << 24) - 1)
        altitude = (word >> 28) & 0xFFFF
        speed = (word >> 18) & 0x03FF
        heading_raw = (word >> 9) & 0x01FF
        iff = (word >> 6) & 0x07
        identity = (word >> 4) & 0x03

        latitude = self._decode_lat_23bit(raw_lat)
        longitude = self._decode_lon_24bit(raw_lon)
        heading = (float(heading_raw) / float(1 << 9)) * 360.0
        identity_probabilities = self._identity_probabilities(identity)

        return {
            "id": f"{j_series.replace('.', '')}-{track_number}",
            "domain": domain,
            "confidence": 85,
            "severity": 70 if identity == 2 else 50,
            "correlatedTrackIds": [],
            "summary": f"{j_series} tactical track {track_number}",
            "lastSeen": datetime.now(timezone.utc).isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "altitude": float(altitude),
            "speed": float(speed),
            "heading": heading,
            "identityProbabilities": identity_probabilities,
            "sourceAttribution": ["jreap-c", j_series],
            "track_number": int(track_number),
            "iff": int(iff),
            "identity_code": int(identity),
            "j_series": j_series,
        }

    def _decode_j13_2_record(self, record: bytes, record_index: int) -> Dict[str, object]:
        word = int.from_bytes(record, byteorder="big", signed=False)
        raw_lat = (word >> 49) & ((1 << 23) - 1)
        raw_lon = (word >> 25) & ((1 << 24) - 1)
        altitude = (word >> 9) & 0xFFFF
        emergency_type = (word >> 1) & 0xFF

        emergency_label = {
            0: "unknown",
            1: "medical",
            2: "distress",
            3: "combat_damage",
            4: "fuel_emergency",
        }.get(int(emergency_type), "unspecified")

        # Tactical context: emergency points are surfaced with elevated severity so
        # operators can rapidly prioritize SAR and combat support decisions.
        return {
            "id": f"J132-{record_index}",
            "domain": "air",
            "confidence": 95,
            "severity": 95,
            "correlatedTrackIds": [],
            "summary": f"J13.2 emergency point ({emergency_label})",
            "lastSeen": datetime.now(timezone.utc).isoformat(),
            "latitude": self._decode_lat_23bit(raw_lat),
            "longitude": self._decode_lon_24bit(raw_lon),
            "altitude": float(altitude),
            "speed": None,
            "heading": None,
            "identityProbabilities": {"unknown": 1.0},
            "sourceAttribution": ["jreap-c", "J13.2"],
            "emergency_type": int(emergency_type),
            "emergency_label": emergency_label,
            "j_series": "J13.2",
        }

    @staticmethod
    def _identity_probabilities(identity_code: int) -> Dict[str, float]:
        if identity_code == 0:
            return {"friendly": 0.2, "hostile": 0.2, "unknown": 0.6}
        if identity_code == 1:
            return {"friendly": 0.75, "hostile": 0.1, "unknown": 0.15}
        if identity_code == 2:
            return {"friendly": 0.05, "hostile": 0.85, "unknown": 0.1}
        return {"friendly": 0.1, "hostile": 0.1, "unknown": 0.8}
