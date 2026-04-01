"""VesselFinder adapter for complementary AIS maritime coverage."""

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

from .config import VesselFinderConfig
from .normalizer import VesselFinderNormalizer


class VesselFinderAdapter(ProviderAdapter):
    """Adapter for VesselFinder vessel and arrival feeds."""

    def __init__(self, mode: OperatingMode = OperatingMode.ONLINE):
        super().__init__(mode=mode)
        self.config = VesselFinderConfig()
        self.secret_provider = SecretProvider(prefix="S3M")
        self.normalizer = VesselFinderNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "maritime-vesselfinder" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        if self._manifest is None:
            self._manifest = ProviderManifest(
                provider_id="maritime-vesselfinder",
                name="VesselFinder",
                category=ProviderCategory.MARITIME,
                tier=ProviderTier.FREEMIUM,
                base_url=self.config.base_url,
                auth_type="api_key",
                rate_limit_rpm=self.config.rate_limit_rpm,
                supported_schemas=["NormalizedVesselTrack"],
                required_env_vars=["S3M_VESSELFINDER_API_KEY"],
                description="Real-time AIS vessel tracking with complementary receiver network coverage.",
                docs_url="https://api.vesselfinder.com/docs",
                airgap_capable=True,
                enabled=True,
                tags=["maritime", "ais", "arrivals"],
            )
        return self._manifest

    def _api_key(self) -> str:
        return self.secret_provider.get("VESSELFINDER_API_KEY") or ""

    def validate_credentials(self) -> bool:
        if self.is_airgapped():
            return (self.fixture_dir / "vessels_persian_gulf.json").exists()
        return bool(self._api_key())

    def _read_fixture(self, name: str) -> Any:
        with (self.fixture_dir / name).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _get_json(self, url: str) -> Any:
        with request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _build_url(self, params: dict[str, Any]) -> str:
        key = self._api_key()
        if not key:
            raise RuntimeError("Missing S3M_VESSELFINDER_API_KEY")
        query = {"userkey": key, **params}
        return f"{self.config.base_url}/vessels?{parse.urlencode(query)}"

    def fetch_vessel(self, mmsi: str) -> dict[str, Any]:
        if self.is_airgapped():
            payload = self._read_fixture("vessel_single.json")
            return {"vessels": payload, "count": len(payload)}
        payload = self._get_json(self._build_url({"mmsi": mmsi}))
        return {"vessels": payload if isinstance(payload, list) else [payload], "count": len(payload)}

    def fetch_zone_vessels(self, zone: str = "persian_gulf") -> dict[str, Any]:
        zone_box = self.config.monitoring_zones.get(zone)
        if not zone_box:
            raise ValueError(f"Unknown monitoring zone: {zone}")
        if self.is_airgapped():
            payload = self._read_fixture("vessels_persian_gulf.json")
            vessels = payload if zone == "persian_gulf" else payload[:8]
        else:
            vessels = self._get_json(
                self._build_url(
                    {
                        "latmin": zone_box["minlat"],
                        "latmax": zone_box["maxlat"],
                        "lonmin": zone_box["minlon"],
                        "lonmax": zone_box["maxlon"],
                    }
                )
            )
        for row in vessels:
            row.setdefault("ZONE_NAME", zone)
        self._last_fetch_at = datetime.now(timezone.utc)
        self._fetch_count += 1
        self._last_health = ProviderHealth.OK
        return {"vessels": vessels, "count": len(vessels), "zone": zone}

    def fetch_port_arrivals(self, port: str = "JUBAIL") -> dict[str, Any]:
        port_norm = str(port).upper()
        if port_norm not in self.config.saudi_ports:
            raise ValueError(f"Unsupported Saudi monitoring port: {port_norm}")
        if self.is_airgapped():
            payload = self._read_fixture("port_arrivals_jubail.json")
            return {"arrivals": payload, "count": len(payload), "port": port_norm}
        key = self._api_key()
        if not key:
            raise RuntimeError("Missing S3M_VESSELFINDER_API_KEY")
        url = f"{self.config.base_url}/expectedArrivals?{parse.urlencode({'userkey': key, 'portname': port_norm})}"
        payload = self._get_json(url)
        return {"arrivals": payload if isinstance(payload, list) else [payload], "count": len(payload), "port": port_norm}

    def fetch_all_saudi_zones(self) -> dict[str, Any]:
        by_zone: dict[str, dict[str, int]] = {}
        merged: dict[str, dict[str, Any]] = {}
        for zone in self.config.monitoring_zones:
            zone_data = self.fetch_zone_vessels(zone=zone)
            by_zone[zone] = {"count": zone_data["count"]}
            for record in zone_data["vessels"]:
                ais = record.get("AIS", {})
                mmsi = str(ais.get("MMSI", "")).strip()
                if not mmsi:
                    continue
                ts_new = self.normalizer._parse_dt(str(ais.get("TIMESTAMP", "")))
                existing = merged.get(mmsi)
                if existing is None:
                    merged[mmsi] = dict(record)
                else:
                    ts_old = self.normalizer._parse_dt(str(existing.get("AIS", {}).get("TIMESTAMP", "")))
                    if ts_new > ts_old:
                        merged[mmsi] = dict(record)
        return {"total_vessels": len(merged), "by_zone": by_zone, "vessels": list(merged.values())}

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        op = params.get("op")
        if op == "vessel":
            return self.fetch_vessel(str(params.get("mmsi", "")))
        if op == "arrivals":
            return self.fetch_port_arrivals(str(params.get("port", "JUBAIL")))
        if op == "all_zones":
            return self.fetch_all_saudi_zones()
        return self.fetch_zone_vessels(str(params.get("zone", "persian_gulf")))

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        if "vessels" in raw_data:
            return self.normalizer.normalize_batch(raw_data.get("vessels", []))
        if "arrivals" in raw_data:
            return self.normalizer.normalize_port_arrivals(raw_data.get("arrivals", []))
        return []

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if self.is_airgapped():
                ok = (self.fixture_dir / "vessels_persian_gulf.json").exists()
                status = ProviderHealth.OK if ok else ProviderHealth.FAILING
                detail = "fixture available" if ok else "fixture missing"
            else:
                ok = self.validate_credentials()
                status = ProviderHealth.OK if ok else ProviderHealth.DEGRADED
                detail = "api key available" if ok else "api key missing"
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
