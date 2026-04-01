"""Windward adapter for maritime AI risk intelligence."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import request

from integration_sdk.auth.secret_provider import SecretProvider
from integration_sdk.base.provider_adapter import (
    OperatingMode,
    ProviderAdapter,
    ProviderCategory,
    ProviderHealth,
    ProviderManifest,
    ProviderTier,
)

from .config import WindwardConfig
from .normalizer import WindwardNormalizer


class WindwardAdapter(ProviderAdapter):
    """Adapter for Windward vessel risk, screening, alerts, and ownership."""

    def __init__(self, mode: OperatingMode = OperatingMode.ONLINE):
        super().__init__(mode=mode)
        self.config = WindwardConfig()
        self.secret_provider = SecretProvider(prefix="S3M")
        self.normalizer = WindwardNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "maritime-windward" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        if self._manifest is None:
            self._manifest = ProviderManifest(
                provider_id="maritime-windward",
                name="Windward Maritime AI",
                category=ProviderCategory.MARITIME,
                tier=ProviderTier.PREMIUM,
                base_url=self.config.base_url,
                auth_type="api_key",
                rate_limit_rpm=self.config.rate_limit_rpm,
                supported_schemas=["NormalizedVesselTrack"],
                required_env_vars=["S3M_WINDWARD_API_KEY"],
                description="Maritime risk analytics, sanctions screening, and suspicious behavior indicators.",
                docs_url="https://api.windward.ai/docs",
                airgap_capable=True,
                enabled=True,
                tags=["maritime", "risk", "sanctions", "dark_activity"],
            )
        return self._manifest

    def _api_key(self) -> str:
        return self.secret_provider.get("WINDWARD_API_KEY") or ""

    def validate_credentials(self) -> bool:
        if self.is_airgapped():
            return (self.fixture_dir / "vessel_risk_high.json").exists()
        return bool(self._api_key())

    def _read_fixture(self, name: str) -> Any:
        with (self.fixture_dir / name).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _headers(self) -> dict[str, str]:
        key = self._api_key()
        if not key:
            raise RuntimeError("Missing S3M_WINDWARD_API_KEY")
        return {"Authorization": f"apikey {key}", "Content-Type": "application/json"}

    def _get_json(self, url: str) -> Any:
        req = request.Request(url, method="GET", headers=self._headers())
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        req = request.Request(url, method="POST", headers=self._headers(), data=json.dumps(payload).encode("utf-8"))
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_vessel_risk(self, mmsi: str) -> dict[str, Any]:
        if self.is_airgapped():
            high = self._read_fixture("vessel_risk_high.json")
            low = self._read_fixture("vessel_risk_low.json")
            profile = high if str(mmsi) == str(high.get("mmsi")) else low
            return {"profile": profile}
        return {"profile": self._get_json(f"{self.config.base_url}/vessels/{mmsi}/risk")}

    def screen_fleet(self, mmsis: list[str]) -> dict[str, Any]:
        if self.is_airgapped():
            data = self._read_fixture("fleet_screening.json")
            results = data.get("results", [])
        else:
            payload = self._post_json(f"{self.config.base_url}/screening/fleet", {"mmsis": mmsis})
            results = payload.get("results", payload if isinstance(payload, list) else [])
        flagged = len([item for item in results if int(item.get("risk_score", 0) or 0) >= self.config.risk_level_thresholds["medium"]])
        clean = max(0, len(results) - flagged)
        return {"results": results, "flagged": flagged, "clean": clean}

    def fetch_alerts(self, zone: str | None = None, severity: str = "high", days_back: int = 7) -> dict[str, Any]:
        if self.is_airgapped():
            alerts = self._read_fixture("alerts_bab_el_mandeb.json")
            if zone:
                alerts = [item for item in alerts if item.get("zone_id") == zone]
            if severity:
                alerts = [item for item in alerts if str(item.get("severity", "")).lower() == severity.lower()]
            return {"alerts": alerts, "count": len(alerts), "zone": zone, "severity": severity}
        since = (datetime.now(timezone.utc) - timedelta(days=days_back)).date().isoformat()
        url = f"{self.config.base_url}/alerts?severity={severity}&since={since}"
        if zone:
            url += f"&zone_id={zone}"
        payload = self._get_json(url)
        alerts = payload.get("alerts", payload if isinstance(payload, list) else [])
        return {"alerts": alerts, "count": len(alerts), "zone": zone, "severity": severity}

    def fetch_ownership(self, mmsi: str) -> dict[str, Any]:
        if self.is_airgapped():
            payload = self._read_fixture("ownership_chain.json")
            payload["mmsi"] = str(mmsi)
            return {"ownership": payload}
        return {"ownership": self._get_json(f"{self.config.base_url}/vessels/{mmsi}/ownership")}

    def screen_saudi_zones(self) -> dict[str, Any]:
        if self.is_airgapped():
            screening = self._read_fixture("fleet_screening.json")
            results = screening.get("results", [])
        else:
            # Tactical context: high-risk maritime corridors are prioritized for screening.
            zone_mmsis = [
                "636092400",
                "636092401",
                "477000100",
                "563001200",
                "403441112",
                "311000987",
            ]
            results = self.screen_fleet(zone_mmsis).get("results", [])

        high_risk = [item for item in results if int(item.get("risk_score", 0) or 0) >= self.config.risk_level_thresholds["high"]]
        sanctions = [
            item
            for item in results
            if bool(item.get("sanctions_screening", {}).get("proximity_to_listed"))
            or bool(item.get("sanctions_proximity"))
        ]
        dark = [
            item
            for item in results
            if any(ind.get("type") == "dark_activity" for ind in item.get("risk_indicators", []))
            or bool(item.get("dark_activity"))
        ]
        return {
            "total_screened": len(results),
            "high_risk": high_risk,
            "sanctioned_proximity": sanctions,
            "dark_activity": dark,
        }

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        op = params.get("op", "risk")
        if op == "risk":
            return self.fetch_vessel_risk(str(params.get("mmsi", "636092400")))
        if op == "screen_fleet":
            return self.screen_fleet(list(params.get("mmsis", [])))
        if op == "alerts":
            return self.fetch_alerts(zone=params.get("zone"), severity=str(params.get("severity", "high")), days_back=int(params.get("days_back", 7)))
        if op == "ownership":
            return self.fetch_ownership(str(params.get("mmsi", "636092400")))
        if op == "screen_saudi_zones":
            return self.screen_saudi_zones()
        return self.fetch_vessel_risk(str(params.get("mmsi", "636092400")))

    def normalize(self, raw_data: dict[str, Any]) -> list[Any]:
        if "profile" in raw_data and isinstance(raw_data["profile"], dict):
            return [self.normalizer.normalize_risk_profile(raw_data["profile"])]
        if "results" in raw_data:
            return [self.normalizer.normalize_risk_profile(item) for item in raw_data.get("results", [])]
        return []

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            if self.is_airgapped():
                ok = (self.fixture_dir / "vessel_risk_high.json").exists()
                status = ProviderHealth.OK if ok else ProviderHealth.FAILING
                detail = "risk fixture available" if ok else "risk fixture missing"
            else:
                _ = self.fetch_vessel_risk("636092400")
                status = ProviderHealth.OK
                detail = "risk endpoint reachable"
            return {
                "status": status,
                "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
                "last_successful_fetch": self._last_fetch_at,
                "error_count": self._error_count,
                "detail": detail,
            }
        except Exception as exc:  # pragma: no cover
            self._error_count += 1
            return {
                "status": ProviderHealth.FAILING,
                "latency_ms": round((time.perf_counter() - start) * 1000.0, 2),
                "last_successful_fetch": self._last_fetch_at,
                "error_count": self._error_count,
                "detail": str(exc),
            }
