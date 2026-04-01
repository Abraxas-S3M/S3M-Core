"""MarineTraffic adapter for tactical maritime vessel surveillance."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from integration_sdk.auth.secret_provider import SecretProvider
from integration_sdk.base.provider_adapter import (
    OperatingMode,
    ProviderAdapter,
    ProviderCategory,
    ProviderHealth,
    ProviderManifest,
    ProviderTier,
)

from .config import MONITORING_ZONES, MarineTrafficConfig
from .normalizer import MarineTrafficNormalizer


class MarineTrafficAdapter(ProviderAdapter):
    """Adapter for MarineTraffic PS/VD/EV/VH feeds."""

    def __init__(self, mode: OperatingMode = OperatingMode.ONLINE):
        super().__init__(mode=mode)
        self.config = MarineTrafficConfig()
        self.secret_provider = SecretProvider(prefix="S3M")
        self.normalizer = MarineTrafficNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "maritime-marinetraffic" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        if self._manifest is None:
            self._manifest = ProviderManifest(
                provider_id="maritime-marinetraffic",
                name="MarineTraffic",
                category=ProviderCategory.MARITIME,
                tier=ProviderTier.FREEMIUM,
                base_url=self.config.base_url,
                auth_type="api_key",
                rate_limit_rpm=self.config.rate_limit_rpm,
                supported_schemas=["NormalizedVesselTrack"],
                required_env_vars=["S3M_MARINETRAFFIC_API_KEY"],
                description="Global AIS vessel tracking and events for maritime domain awareness.",
                docs_url="https://www.marinetraffic.com/en/ais-api-services",
                airgap_capable=True,
                enabled=True,
                tags=["maritime", "ais", "tracking", "events"],
            )
        return self._manifest

    def _api_key(self) -> str:
        return self.secret_provider.get("MARINETRAFFIC_API_KEY") or ""

    def validate_credentials(self) -> bool:
        if self.is_airgapped():
            return (self.fixture_dir / "ps01_persian_gulf.json").exists()
        key = self._api_key()
        if not key:
            return False
        try:
            _ = self.fetch_vessel_position("211000000")
            return True
        except Exception:
            return False

    def _read_fixture(self, name: str) -> Any:
        with (self.fixture_dir / name).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _get_json(self, url: str) -> Any:
        with request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _online_zone_url(self, zone: dict[str, float], timespan_minutes: int) -> str:
        key = self._api_key()
        if not key:
            raise RuntimeError("Missing S3M_MARINETRAFFIC_API_KEY")
        return (
            f"{self.config.base_url}/exportvessels/v:8/{parse.quote(key)}"
            f"/MINLAT:{zone['minlat']}/MAXLAT:{zone['maxlat']}"
            f"/MINLON:{zone['minlon']}/MAXLON:{zone['maxlon']}"
            f"/timespan:{timespan_minutes}/protocol:jsono"
        )

    def fetch_zone_vessels(self, zone: str = "persian_gulf", timespan_minutes: int = 60) -> dict[str, Any]:
        zone_box = MONITORING_ZONES.get(zone)
        if not zone_box:
            raise ValueError(f"Unknown monitoring zone: {zone}")

        if self.is_airgapped():
            filename = "ps01_persian_gulf.json" if zone == "persian_gulf" else "ps01_red_sea.json"
            vessels = self._read_fixture(filename)
        else:
            vessels = self._get_json(self._online_zone_url(zone_box, timespan_minutes))

        for item in vessels:
            item.setdefault("ZONE_NAME", zone)
        self._last_fetch_at = datetime.now(timezone.utc)
        self._fetch_count += 1
        self._last_health = ProviderHealth.OK
        return {
            "vessels": vessels,
            "count": len(vessels),
            "zone": zone,
            "timespan_minutes": timespan_minutes,
        }

    def fetch_vessel_position(self, mmsi: str) -> dict[str, Any]:
        if self.is_airgapped():
            vessels = self._read_fixture("ps01_persian_gulf.json")
            vessel = next((v for v in vessels if str(v.get("MMSI")) == str(mmsi)), vessels[0] if vessels else {})
            return {"vessel": vessel}
        key = self._api_key()
        url = f"{self.config.base_url}/exportvessel/v:5/{parse.quote(key)}/mmsi:{mmsi}/protocol:jsono"
        return {"vessel": self._get_json(url)}

    def fetch_vessel_details(self, mmsi: str) -> dict[str, Any]:
        if self.is_airgapped():
            detail = self._read_fixture("vd01_vessel_detail.json")
            detail.setdefault("MMSI", mmsi)
            return {"detail": detail}
        key = self._api_key()
        url = f"{self.config.base_url}/exportvessel/v:5/{parse.quote(key)}/mmsi:{mmsi}/protocol:jsono"
        return {"detail": self._get_json(url)}

    def fetch_vessel_events(self, mmsi: str, event_types: list[int] | None = None) -> dict[str, Any]:
        event_types = event_types or [1, 2, 11, 12, 19, 20]
        if self.is_airgapped():
            events = [evt for evt in self._read_fixture("ev01_events.json") if str(evt.get("MMSI")) == str(mmsi)]
            if not events:
                events = self._read_fixture("ev01_events.json")
            events = [evt for evt in events if int(evt.get("EVENT_TYPE", -1)) in event_types]
            return {"events": events, "count": len(events), "mmsi": mmsi}

        key = self._api_key()
        all_events: list[dict[str, Any]] = []
        for et in event_types:
            url = f"{self.config.base_url}/exportevents/v:2/{parse.quote(key)}/mmsi:{mmsi}/eventtype:{et}/protocol:jsono"
            payload = self._get_json(url)
            if isinstance(payload, list):
                all_events.extend(payload)
        return {"events": all_events, "count": len(all_events), "mmsi": mmsi}

    def fetch_voyage_history(self, mmsi: str, from_date: str, to_date: str) -> dict[str, Any]:
        if self.is_airgapped():
            vessels = self._read_fixture("ps01_persian_gulf.json")
            path = [v for v in vessels if str(v.get("MMSI")) == str(mmsi)] or vessels[:3]
            return {"history": path, "count": len(path), "mmsi": mmsi, "from_date": from_date, "to_date": to_date}
        key = self._api_key()
        url = (
            f"{self.config.base_url}/exportvessels/v:3/{parse.quote(key)}"
            f"/mmsi:{mmsi}/fromdate:{from_date}/todate:{to_date}/protocol:jsono"
        )
        payload = self._get_json(url)
        return {"history": payload if isinstance(payload, list) else [payload], "mmsi": mmsi}

    def fetch_all_saudi_zones(self, timespan_minutes: int = 60) -> dict[str, Any]:
        by_zone: dict[str, dict[str, Any]] = {}
        merged: dict[str, dict[str, Any]] = {}
        for zone in MONITORING_ZONES:
            zone_data = self.fetch_zone_vessels(zone=zone, timespan_minutes=timespan_minutes)
            by_zone[zone] = {"count": zone_data["count"]}
            for vessel in zone_data["vessels"]:
                mmsi = str(vessel.get("MMSI", "")).strip()
                if not mmsi:
                    continue
                if mmsi not in merged:
                    merged[mmsi] = dict(vessel)
                    merged[mmsi]["ZONE_NAME"] = zone
                else:
                    merged[mmsi]["ZONE_NAME"] = f"{merged[mmsi].get('ZONE_NAME', zone)}|{zone}"
                    ts_a = self.normalizer._parse_dt(merged[mmsi].get("TIMESTAMP"))
                    ts_b = self.normalizer._parse_dt(vessel.get("TIMESTAMP"))
                    if ts_b > ts_a:
                        merged[mmsi].update(vessel)
                        merged[mmsi]["ZONE_NAME"] = zone
        return {"total_vessels": len(merged), "by_zone": by_zone, "vessels": list(merged.values())}

    def fetch_ais_gap_events(self, zone: str | None = None, days_back: int = 7) -> dict[str, Any]:
        if self.is_airgapped():
            events = self._read_fixture("ais_gap_events.json")
            return {"gaps": events, "count": len(events), "zone": zone, "days_back": days_back}

        if zone:
            vessels = self.fetch_zone_vessels(zone=zone, timespan_minutes=min(days_back * 1440, 10080)).get("vessels", [])
        else:
            vessels = self.fetch_all_saudi_zones(timespan_minutes=min(days_back * 1440, 10080)).get("vessels", [])

        gap_events: list[dict[str, Any]] = []
        for vessel in vessels[:50]:
            mmsi = str(vessel.get("MMSI", ""))
            payload = self.fetch_vessel_events(mmsi=mmsi, event_types=[19, 20])
            gap_events.extend(payload.get("events", []))
        return {"gaps": gap_events, "count": len(gap_events), "zone": zone, "days_back": days_back}

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if params.get("op") == "vessel":
            return self.fetch_vessel_position(str(params["mmsi"]))
        if params.get("op") == "details":
            return self.fetch_vessel_details(str(params["mmsi"]))
        if params.get("op") == "events":
            return self.fetch_vessel_events(str(params["mmsi"]), params.get("event_types"))
        if params.get("op") == "voyage":
            return self.fetch_voyage_history(str(params["mmsi"]), str(params["from_date"]), str(params["to_date"]))
        if params.get("op") == "all_zones":
            return self.fetch_all_saudi_zones(timespan_minutes=int(params.get("timespan_minutes", 60)))
        if params.get("op") == "ais_gaps":
            return self.fetch_ais_gap_events(zone=params.get("zone"), days_back=int(params.get("days_back", 7)))
        return self.fetch_zone_vessels(
            zone=str(params.get("zone", "persian_gulf")),
            timespan_minutes=int(params.get("timespan_minutes", self.config.default_timespan_minutes)),
        )

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        if "vessels" in raw_data:
            return self.normalizer.normalize_batch(raw_data.get("vessels", []))
        if "vessel" in raw_data and isinstance(raw_data["vessel"], dict):
            return [self.normalizer.normalize_vessel(raw_data["vessel"])]
        return []

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if self.is_airgapped():
                ok = (self.fixture_dir / "ps01_persian_gulf.json").exists()
                detail = "fixture available" if ok else "fixture missing"
                status = ProviderHealth.OK if ok else ProviderHealth.FAILING
            else:
                data = self.fetch_zone_vessels("persian_gulf", 60)
                status = ProviderHealth.OK if data.get("count", 0) >= 0 else ProviderHealth.DEGRADED
                detail = f"zone query completed with {data.get('count', 0)} vessels"
            latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
            self._last_health = status
            return {
                "status": status,
                "latency_ms": latency_ms,
                "last_successful_fetch": self._last_fetch_at,
                "error_count": self._error_count,
                "detail": detail,
            }
        except Exception as exc:  # pragma: no cover
            self._error_count += 1
            self._last_health = ProviderHealth.FAILING
            return {
                "status": ProviderHealth.FAILING,
                "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
                "last_successful_fetch": self._last_fetch_at,
                "error_count": self._error_count,
                "detail": str(exc),
            }
