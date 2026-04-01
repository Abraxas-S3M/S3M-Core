"""Normalization helpers for simulation-only OGC SensorThings payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.providers.sim_sensorthings.config import S3M_SENSOR_TYPES


class SensorThingsNormalizer:
    """Convert SensorThings entities into S3M sensor fusion-compatible dicts."""

    def normalize_observation(self, obs: dict[str, Any]) -> dict[str, Any]:
        ts = str(obs.get("phenomenonTime") or obs.get("timestamp") or datetime.now(timezone.utc).isoformat())
        datastream = obs.get("Datastream") or {}
        thing = datastream.get("Thing") or obs.get("Thing") or {}
        location = thing.get("Location") or thing.get("Locations") or {}
        if isinstance(location, list):
            location = location[0] if location else {}
        coords = location.get("coordinates", [0.0, 0.0, 0.0])
        if not isinstance(coords, list):
            coords = [0.0, 0.0, 0.0]
        while len(coords) < 3:
            coords.append(0.0)
        sensor_type = str(thing.get("sensor_type", obs.get("sensor_type", "ground_radar")))

        return {
            "sensor_id": str(thing.get("@iot.id", thing.get("id", "unknown-sensor"))),
            "sensor_type": sensor_type,
            "property": str(datastream.get("name", obs.get("property", "unknown_property"))),
            "value": obs.get("result"),
            "timestamp": ts,
            "position": (float(coords[1]), float(coords[0]), float(coords[2])),
            "unit": str((datastream.get("unitOfMeasurement") or {}).get("symbol", obs.get("unit", ""))),
            "quality": str(obs.get("resultQuality", "nominal")),
        }

    def normalize_thing(self, thing: dict[str, Any]) -> dict[str, Any]:
        locations = thing.get("Locations", [])
        location = locations[0] if locations else {}
        coords = (location.get("location") or {}).get("coordinates", [0.0, 0.0, 0.0])
        if not isinstance(coords, list):
            coords = [0.0, 0.0, 0.0]
        while len(coords) < 3:
            coords.append(0.0)
        sensor_type = str(thing.get("sensor_type", "ground_radar"))
        if sensor_type not in S3M_SENSOR_TYPES:
            sensor_type = "ground_radar"
        datastreams = [str(ds.get("name", "")) for ds in thing.get("Datastreams", [])]
        return {
            "thing_id": str(thing.get("@iot.id", thing.get("id", "unknown-thing"))),
            "name": str(thing.get("name", "unknown")),
            "sensor_type": sensor_type,
            "position": (float(coords[1]), float(coords[0]), float(coords[2])),
            "datastreams": datastreams,
            "status": str(thing.get("status", "active")),
        }
