"""STANAG 4609 FMV metadata packet construction and catalog registration."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import struct
from typing import Any, Mapping
from uuid import uuid4

from services.interop.fmv.klv_encoder import KLVEncoder


class FMVMetadataBuilder:
    """Build and parse MISB 0601 KLV metadata for tactical FMV workflows."""

    def __init__(
        self,
        *,
        klv_encoder: KLVEncoder | None = None,
        config: dict[str, Any] | None = None,
        nsili_catalog_path: str | Path = "data/interop/nsili_fmv_catalog.json",
    ) -> None:
        self.klv_encoder = klv_encoder or KLVEncoder()
        defaults = {
            "klv_standard": "MISB_0601",
            "embed_in_stream": False,
            "register_in_nsili": True,
        }
        self.config = defaults | dict(config or {})
        self.nsili_catalog_path = Path(nsili_catalog_path)
        self.nsili_catalog_path.parent.mkdir(parents=True, exist_ok=True)

    def build_metadata_packet(self, uav_status: dict, payload_status: dict, timestamp: float) -> bytes:
        """Build a binary KLV packet from UAV and payload telemetry snapshots."""
        if not isinstance(uav_status, dict):
            raise TypeError("uav_status must be a dictionary")
        if not isinstance(payload_status, dict):
            raise TypeError("payload_status must be a dictionary")
        ts_seconds = self._ensure_numeric(timestamp, "timestamp")
        timestamp_us = int(ts_seconds * 1_000_000.0)

        heading = self._extract_numeric(
            uav_status,
            ("platform_heading",),
            ("heading",),
            ("orientation", "heading"),
            ("attitude", "heading"),
            default=0.0,
        )
        pitch = self._extract_numeric(
            uav_status,
            ("platform_pitch",),
            ("pitch",),
            ("orientation", "pitch"),
            ("attitude", "pitch"),
            default=0.0,
        )
        roll = self._extract_numeric(
            uav_status,
            ("platform_roll",),
            ("roll",),
            ("orientation", "roll"),
            ("attitude", "roll"),
            default=0.0,
        )

        sensor_lat = self._extract_numeric(
            payload_status,
            ("sensor_latitude",),
            ("sensor", "latitude"),
            ("sensor_position", "latitude"),
            default=None,
        )
        sensor_lon = self._extract_numeric(
            payload_status,
            ("sensor_longitude",),
            ("sensor", "longitude"),
            ("sensor_position", "longitude"),
            default=None,
        )
        sensor_alt = self._extract_numeric(
            payload_status,
            ("sensor_altitude",),
            ("sensor", "altitude"),
            ("sensor_position", "altitude"),
            ("sensor_altitude_hae",),
            default=None,
        )
        if sensor_lat is None:
            sensor_lat = self._extract_numeric(
                uav_status,
                ("latitude",),
                ("position", "latitude"),
                default=0.0,
            )
        if sensor_lon is None:
            sensor_lon = self._extract_numeric(
                uav_status,
                ("longitude",),
                ("position", "longitude"),
                default=0.0,
            )
        if sensor_alt is None:
            sensor_alt = self._extract_numeric(
                uav_status,
                ("altitude",),
                ("position", "altitude"),
                ("altitude_hae",),
                default=0.0,
            )

        horizontal_fov = self._extract_numeric(
            payload_status,
            ("horizontal_fov",),
            ("fov", "horizontal"),
            ("sensor_fov", "horizontal"),
            default=0.0,
        )
        vertical_fov = self._extract_numeric(
            payload_status,
            ("vertical_fov",),
            ("fov", "vertical"),
            ("sensor_fov", "vertical"),
            default=0.0,
        )

        target_lat = self._extract_numeric(
            payload_status,
            ("target_latitude",),
            ("target", "latitude"),
            ("target_location", "latitude"),
            ("aimpoint", "latitude"),
            default=None,
        )
        target_lon = self._extract_numeric(
            payload_status,
            ("target_longitude",),
            ("target", "longitude"),
            ("target_location", "longitude"),
            ("aimpoint", "longitude"),
            default=None,
        )
        version = int(
            self._extract_numeric(
                payload_status,
                ("uas_local_set_version",),
                ("klv_version",),
                default=13,
            )
        )
        if version < 0 or version > 255:
            raise ValueError("uas_local_set_version must be in range 0..255")

        fields: list[tuple[int, bytes]] = [
            (KLVEncoder.KEY_UNIX_TIMESTAMP, struct.pack(">Q", timestamp_us)),
            (KLVEncoder.KEY_PLATFORM_HEADING, struct.pack(">d", heading)),
            (KLVEncoder.KEY_PLATFORM_PITCH, struct.pack(">d", pitch)),
            (KLVEncoder.KEY_PLATFORM_ROLL, struct.pack(">d", roll)),
            (KLVEncoder.KEY_SENSOR_LATITUDE, struct.pack(">d", sensor_lat)),
            (KLVEncoder.KEY_SENSOR_LONGITUDE, struct.pack(">d", sensor_lon)),
            (KLVEncoder.KEY_SENSOR_ALTITUDE, struct.pack(">d", sensor_alt)),
            (KLVEncoder.KEY_SENSOR_HORIZONTAL_FOV, struct.pack(">d", horizontal_fov)),
            (KLVEncoder.KEY_SENSOR_VERTICAL_FOV, struct.pack(">d", vertical_fov)),
            (KLVEncoder.KEY_UAS_LOCAL_SET_VERSION, struct.pack(">B", version)),
        ]
        if target_lat is not None:
            fields.append((KLVEncoder.KEY_TARGET_LATITUDE, struct.pack(">d", target_lat)))
        if target_lon is not None:
            fields.append((KLVEncoder.KEY_TARGET_LONGITUDE, struct.pack(">d", target_lon)))

        encoded_parts = [self.klv_encoder.encode_klv(key, value) for key, value in fields]
        return b"".join(encoded_parts)

    def parse_metadata_packet(self, data: bytes) -> dict:
        """Parse a binary KLV packet into structured FMV metadata fields."""
        values: dict[str, Any] = {}
        for key, payload in self.klv_encoder.decode_klv(data):
            if key == KLVEncoder.KEY_UNIX_TIMESTAMP:
                if len(payload) != 8:
                    raise ValueError("invalid timestamp field length")
                values["timestamp"] = struct.unpack(">Q", payload)[0] / 1_000_000.0
            elif key in {
                KLVEncoder.KEY_PLATFORM_HEADING,
                KLVEncoder.KEY_PLATFORM_PITCH,
                KLVEncoder.KEY_PLATFORM_ROLL,
                KLVEncoder.KEY_SENSOR_LATITUDE,
                KLVEncoder.KEY_SENSOR_LONGITUDE,
                KLVEncoder.KEY_SENSOR_ALTITUDE,
                KLVEncoder.KEY_SENSOR_HORIZONTAL_FOV,
                KLVEncoder.KEY_SENSOR_VERTICAL_FOV,
                KLVEncoder.KEY_TARGET_LATITUDE,
                KLVEncoder.KEY_TARGET_LONGITUDE,
            }:
                if len(payload) != 8:
                    raise ValueError(f"invalid floating-point field length for key={key}")
                values[key] = struct.unpack(">d", payload)[0]
            elif key == KLVEncoder.KEY_UAS_LOCAL_SET_VERSION:
                if len(payload) != 1:
                    raise ValueError("invalid UAS local set version field length")
                values["uas_local_set_version"] = struct.unpack(">B", payload)[0]

        target_location: dict[str, float] | None = None
        if KLVEncoder.KEY_TARGET_LATITUDE in values and KLVEncoder.KEY_TARGET_LONGITUDE in values:
            target_location = {
                "latitude": float(values[KLVEncoder.KEY_TARGET_LATITUDE]),
                "longitude": float(values[KLVEncoder.KEY_TARGET_LONGITUDE]),
            }

        return {
            "timestamp": values.get("timestamp"),
            "platform_position": {
                "heading_deg": float(values.get(KLVEncoder.KEY_PLATFORM_HEADING, 0.0)),
                "pitch_deg": float(values.get(KLVEncoder.KEY_PLATFORM_PITCH, 0.0)),
                "roll_deg": float(values.get(KLVEncoder.KEY_PLATFORM_ROLL, 0.0)),
            },
            "sensor_position": {
                "latitude": float(values.get(KLVEncoder.KEY_SENSOR_LATITUDE, 0.0)),
                "longitude": float(values.get(KLVEncoder.KEY_SENSOR_LONGITUDE, 0.0)),
                "altitude_hae_m": float(values.get(KLVEncoder.KEY_SENSOR_ALTITUDE, 0.0)),
            },
            "target_location": target_location,
            "fov": {
                "horizontal_deg": float(values.get(KLVEncoder.KEY_SENSOR_HORIZONTAL_FOV, 0.0)),
                "vertical_deg": float(values.get(KLVEncoder.KEY_SENSOR_VERTICAL_FOV, 0.0)),
            },
            "uas_local_set_version": int(values.get("uas_local_set_version", 0)),
        }

    def register_with_nsili(self, metadata: dict, video_reference: str) -> str:
        """Register FMV metadata as a NSILI VIDEO product and return product ID."""
        if not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")
        if not isinstance(video_reference, str) or not video_reference.strip():
            raise ValueError("video_reference must be a non-empty string")

        product_id = f"fmv-{uuid4().hex[:12]}"
        record = {
            "productId": product_id,
            "productType": "VIDEO",
            "videoReference": video_reference.strip(),
            "metadata": metadata,
            "registeredAt": datetime.now(timezone.utc).isoformat(),
            "standard": self.config.get("klv_standard", "MISB_0601"),
        }
        if not bool(self.config.get("register_in_nsili", True)):
            return product_id

        self._append_offline_catalog(record)
        return product_id

    def _extract_numeric(
        self,
        source: Mapping[str, Any],
        *paths: tuple[str, ...],
        default: float | None = None,
    ) -> float | None:
        if not isinstance(source, Mapping):
            raise TypeError("source must be a mapping")
        for path in paths:
            value = self._nested_lookup(source, path)
            if value is None:
                continue
            if isinstance(value, bool):
                raise TypeError(f"numeric field {'/'.join(path)} cannot be boolean")
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    continue
                try:
                    return float(text)
                except ValueError as exc:
                    raise ValueError(f"invalid numeric value for {'/'.join(path)}") from exc
            raise TypeError(f"invalid type for numeric field {'/'.join(path)}")
        return default

    def _nested_lookup(self, source: Mapping[str, Any], path: tuple[str, ...]) -> Any | None:
        current: Any = source
        for key in path:
            if not isinstance(current, Mapping):
                return None
            if key not in current:
                return None
            current = current[key]
        return current

    def _ensure_numeric(self, value: Any, field_name: str) -> float:
        if isinstance(value, bool):
            raise TypeError(f"{field_name} must be numeric")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError(f"{field_name} cannot be blank")
            try:
                return float(text)
            except ValueError as exc:
                raise ValueError(f"{field_name} must be numeric") from exc
        raise TypeError(f"{field_name} must be numeric")

    def _load_offline_catalog(self) -> list[dict[str, Any]]:
        if not self.nsili_catalog_path.exists():
            return []
        try:
            payload = json.loads(self.nsili_catalog_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _append_offline_catalog(self, record: dict[str, Any]) -> None:
        rows = self._load_offline_catalog()
        rows.append(record)
        self.nsili_catalog_path.write_text(
            json.dumps(rows, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
