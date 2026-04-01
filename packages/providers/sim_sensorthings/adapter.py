"""Simulation-only OGC SensorThings adapter with offline stub support."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import socket
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest
from packages.providers.sim_sensorthings.config import SensorThingsConfig
from packages.providers.sim_sensorthings.normalizer import SensorThingsNormalizer


class SensorThingsAdapter(ProviderAdapter):
    provider_id = "sim-sensorthings"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = SensorThingsConfig()
        self.normalizer = SensorThingsNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "sim-sensorthings" / "fixtures"
        self._stub = True
        self._registered_things: dict[str, dict[str, Any]] = {}
        self._datastream_values: dict[str, list[dict[str, Any]]] = {}
        self._subscriptions: set[str] = set()

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="C4I_INTEROP",
            tier="OPEN_STANDARD",
            auth_type="none",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=[],
            description="OGC SensorThings simulation adapter for distributed sensor network interoperability. SIMULATION ONLY.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            self._stub = True
            return True
        try:
            parsed = parse.urlparse(self.config.base_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            with socket.create_connection((host, int(port)), timeout=0.8):
                self._stub = False
                return True
        except Exception:
            self._stub = True
            return True

    def _fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def get_things(self) -> list[dict[str, Any]]:
        if self._stub:
            return list(self._fixture("things.json").get("value", []))
        url = f"{self.config.base_url}/Things"
        with request.urlopen(url, timeout=8) as resp:
            return list(self._read_json_bytes(resp.read()).get("value", []))

    @staticmethod
    def _read_json_bytes(payload: bytes) -> dict[str, Any]:
        return json.loads(payload.decode("utf-8"))

    def get_observations(
        self,
        datastream_id: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        top = min(max(1, int(limit)), int(self.config.odata_max_top))
        if self._stub:
            fixture = "observations_radar.json"
            if datastream_id and "weather" in datastream_id.lower():
                fixture = "observations_weather.json"
            rows = list(self._fixture(fixture).get("value", []))
            if since:
                rows = [row for row in rows if str(row.get("phenomenonTime", "")) >= since]
            return rows[:top]

        query = f"$top={top}"
        if since:
            query += f"&$filter=phenomenonTime gt {since}"
        if datastream_id:
            url = f"{self.config.base_url}/Datastreams({datastream_id})/Observations?{query}"
        else:
            url = f"{self.config.base_url}/Observations?{query}"
        with request.urlopen(url, timeout=8) as resp:
            return list(self._read_json_bytes(resp.read()).get("value", []))

    def get_latest_observations(self, thing_id: str) -> dict[str, Any]:
        observations = self.get_observations(limit=200)
        latest_by_stream: dict[str, dict[str, Any]] = {}
        for obs in observations:
            stream = str((obs.get("Datastream") or {}).get("@iot.id", "unknown"))
            prev = latest_by_stream.get(stream)
            if prev is None or str(obs.get("phenomenonTime", "")) > str(prev.get("phenomenonTime", "")):
                latest_by_stream[stream] = obs
        return {"thing_id": thing_id, "latest": latest_by_stream}

    def register_s3m_sensor(self, sensor_type: str, name: str, position: tuple[float, float, float]) -> dict[str, Any]:
        sensor_type_norm = str(sensor_type).strip().lower()
        if sensor_type_norm not in self.config.s3m_sensor_types:
            raise ValueError(f"Unsupported sensor_type: {sensor_type}")
        thing_id = f"thing-{len(self._registered_things) + 1:03d}"
        datastreams: list[str] = []
        for prop in self.config.s3m_sensor_types[sensor_type_norm]["properties"]:
            ds_id = f"{thing_id}-{prop}"
            datastreams.append(ds_id)
            self._datastream_values.setdefault(ds_id, [])
        self._registered_things[thing_id] = {
            "@iot.id": thing_id,
            "name": name,
            "sensor_type": sensor_type_norm,
            "position": tuple(position),
            "datastreams": datastreams,
        }
        return {"thing_id": thing_id, "sensor_type": sensor_type_norm, "datastreams": datastreams}

    def publish_observation(self, datastream_id: str, value: float, timestamp: str | None = None) -> dict[str, Any]:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        record = {"phenomenonTime": ts, "result": value}
        self._datastream_values.setdefault(datastream_id, []).append(record)
        return {"datastream_id": datastream_id, "published": True, "observation": record}

    def subscribe_sensor(self, thing_id: str) -> dict[str, Any]:
        self._subscriptions.add(thing_id)
        return {"thing_id": thing_id, "subscribed": True, "mode": "polling"}

    def feed_to_sensor_fusion(self, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Tactical context: normalize distributed observation feeds into a common
        # SensorReading-like contract for cross-domain fusion in rehearsals.
        return [self.normalizer.normalize_observation(obs) for obs in observations]

    def fetch(self, params: dict[str, Any]) -> Any:
        action = str(params.get("action", "things"))
        if action == "observations":
            return self.get_observations(
                datastream_id=params.get("datastream_id"),
                since=params.get("since"),
                limit=int(params.get("limit", 100)),
            )
        if action == "latest":
            return self.get_latest_observations(str(params.get("thing_id", "")))
        return self.get_things()

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, list):
            if raw_data and "phenomenonTime" in raw_data[0]:
                return [self.normalizer.normalize_observation(row) for row in raw_data]
            if raw_data and "Datastreams" in raw_data[0]:
                return [self.normalizer.normalize_thing(row) for row in raw_data]
        if isinstance(raw_data, dict) and "phenomenonTime" in raw_data:
            return self.normalizer.normalize_observation(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "stub_mode": self._stub,
            "registered_sensors": len(self._registered_things),
            "subscriptions": len(self._subscriptions),
        }
