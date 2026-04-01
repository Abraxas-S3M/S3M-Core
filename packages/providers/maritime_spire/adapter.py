"""Spire Maritime adapter for satellite and terrestrial AIS coverage."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
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

from .config import SpireConfig, ZONE_CENTERS
from .normalizer import SpireNormalizer


class SpireMaritimeAdapter(ProviderAdapter):
    """Adapter for Spire vessel position and fleet APIs."""

    def __init__(self, mode: OperatingMode = OperatingMode.ONLINE):
        super().__init__(mode=mode)
        self.config = SpireConfig()
        self.secret_provider = SecretProvider(prefix="S3M")
        self.normalizer = SpireNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "maritime-spire" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        if self._manifest is None:
            self._manifest = ProviderManifest(
                provider_id="maritime-spire",
                name="Spire Maritime",
                category=ProviderCategory.MARITIME,
                tier=ProviderTier.PREMIUM,
                base_url=self.config.base_url,
                auth_type="api_key",
                rate_limit_rpm=self.config.rate_limit_rpm,
                supported_schemas=["NormalizedVesselTrack"],
                required_env_vars=["S3M_SPIRE_API_TOKEN"],
                description="Satellite AIS coverage for open-ocean maritime monitoring.",
                docs_url="https://api.spire.com/",
                airgap_capable=True,
                enabled=True,
                tags=["maritime", "ais", "satellite"],
            )
        return self._manifest

    def _token(self) -> str:
        return self.secret_provider.get("SPIRE_API_TOKEN") or ""

    def _read_fixture(self, filename: str) -> Any:
        with (self.fixture_dir / filename).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _request_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        token = self._token()
        if not token:
            raise RuntimeError("Missing S3M_SPIRE_API_TOKEN")
        query = parse.urlencode(params)
        req = request.Request(f"{self.config.base_url}{endpoint}?{query}", method="GET")
        req.add_header("Authorization", f"Bearer {token}")
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def validate_credentials(self) -> bool:
        if self.is_airgapped():
            return (self.fixture_dir / "vessels_persian_gulf.json").exists()
        if not self._token():
            return False
        try:
            _ = self.fetch_zone_vessels("persian_gulf")
            return True
        except Exception:
            return False

    def fetch_zone_vessels(self, zone: str = "persian_gulf") -> dict[str, Any]:
        center = ZONE_CENTERS.get(zone)
        if not center:
            raise ValueError(f"Unknown Spire monitoring zone: {zone}")

        if self.is_airgapped():
            payload = self._read_fixture("vessels_persian_gulf.json")
            vessels = payload.get("data", [])
        else:
            vessels: list[dict[str, Any]] = []
            cursor = ""
            while True:
                params: dict[str, Any] = {
                    "latitude": center["lat"],
                    "longitude": center["lon"],
                    "radius": int(center["radius_m"]),
                }
                if cursor:
                    params["cursor"] = cursor
                payload = self._request_json("/vessels/positions", params)
                vessels.extend(payload.get("data", []))
                cursor = str(payload.get("paging", {}).get("next") or "")
                if not cursor:
                    break

        collection_types = {"satellite": 0, "terrestrial": 0}
        for vessel in vessels:
            ctype = str(vessel.get("position", {}).get("collection_type", "terrestrial")).lower()
            if ctype == "satellite":
                collection_types["satellite"] += 1
            else:
                collection_types["terrestrial"] += 1
            vessel.setdefault("_zone", zone)
        self._last_fetch_at = datetime.now(timezone.utc)
        self._fetch_count += 1
        self._last_health = ProviderHealth.OK
        return {
            "vessels": vessels,
            "count": len(vessels),
            "zone": zone,
            "collection_types": collection_types,
        }

    def fetch_vessel_history(self, mmsi: str, days_back: int = 7) -> dict[str, Any]:
        if self.is_airgapped():
            payload = self._read_fixture("vessel_history.json")
            history = payload.get("data", [])
            for item in history:
                if str(item.get("mmsi", "")) != str(mmsi):
                    item["mmsi"] = str(mmsi)
            return {"mmsi": mmsi, "history": history, "count": len(history)}
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days_back)
        payload = self._request_json(
            "/vessels/positions",
            {"mmsi": mmsi, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        )
        history = payload.get("data", [])
        return {"mmsi": mmsi, "history": history, "count": len(history)}

    def fetch_fleet_by_flag(self, flag: str = "SA") -> dict[str, Any]:
        if self.is_airgapped():
            data = self._read_fixture("vessels_persian_gulf.json").get("data", [])
            fleet = [item for item in data if str(item.get("flag", "")).upper() == flag.upper()]
            return {"flag": flag.upper(), "vessels": fleet, "count": len(fleet)}
        payload = self._request_json("/vessels", {"flag": flag.upper()})
        fleet = payload.get("data", [])
        return {"flag": flag.upper(), "vessels": fleet, "count": len(fleet)}

    def fetch_all_saudi_zones(self) -> dict[str, Any]:
        merged: dict[str, dict[str, Any]] = {}
        by_zone: dict[str, int] = {}
        for zone in ZONE_CENTERS:
            payload = self.fetch_zone_vessels(zone)
            by_zone[zone] = payload["count"]
            for vessel in payload.get("vessels", []):
                mmsi = str(vessel.get("mmsi", "")).strip()
                if not mmsi:
                    continue
                if mmsi not in merged:
                    merged[mmsi] = dict(vessel)
                else:
                    existing_ts = self.normalizer._parse_dt(merged[mmsi].get("position", {}).get("timestamp"))
                    incoming_ts = self.normalizer._parse_dt(vessel.get("position", {}).get("timestamp"))
                    if incoming_ts >= existing_ts:
                        merged[mmsi] = dict(vessel)
        return {"total_vessels": len(merged), "by_zone": by_zone, "vessels": list(merged.values())}

    def detect_satellite_only_vessels(self, zone: str) -> list[dict[str, Any]]:
        payload = self.fetch_zone_vessels(zone)
        output: list[dict[str, Any]] = []
        for vessel in payload.get("vessels", []):
            history = vessel.get("recent_collection_types") or [vessel.get("position", {}).get("collection_type")]
            values = {str(item).lower() for item in history if item}
            if values == {"satellite"}:
                output.append(vessel)
        return output

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        op = params.get("op", "zone")
        if op == "history":
            return self.fetch_vessel_history(str(params["mmsi"]), int(params.get("days_back", 7)))
        if op == "fleet":
            return self.fetch_fleet_by_flag(str(params.get("flag", "SA")))
        if op == "all_zones":
            return self.fetch_all_saudi_zones()
        if op == "satellite_only":
            return {"vessels": self.detect_satellite_only_vessels(str(params.get("zone", "persian_gulf")))}
        return self.fetch_zone_vessels(str(params.get("zone", "persian_gulf")))

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        vessels = raw_data.get("vessels") if isinstance(raw_data, dict) else None
        if vessels is None and isinstance(raw_data, dict) and "data" in raw_data:
            vessels = raw_data["data"]
        if isinstance(vessels, list):
            return self.normalizer.normalize_batch(vessels)
        return []

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if self.is_airgapped():
                ok = (self.fixture_dir / "vessels_persian_gulf.json").exists()
                status = ProviderHealth.OK if ok else ProviderHealth.FAILING
                detail = "fixture available" if ok else "fixture missing"
            else:
                payload = self.fetch_zone_vessels("persian_gulf")
                status = ProviderHealth.OK
                detail = f"fetched {payload.get('count', 0)} vessels"
            self._last_health = status
            return {
                "status": status,
                "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
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
