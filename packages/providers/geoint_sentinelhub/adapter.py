"""Sentinel Hub adapter for processed imagery and geospatial catalog queries."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest
from packages.providers.geoint_sentinelhub.config import SentinelHubConfig
from packages.providers.geoint_sentinelhub.normalizer import SentinelHubNormalizer


class SentinelHubAdapter(ProviderAdapter):
    provider_id = "geoint-sentinelhub"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = SentinelHubConfig()
        self.normalizer = SentinelHubNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "geoint-sentinelhub" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="FREEMIUM",
            auth_type="oauth2",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["SENTINELHUB_CLIENT_ID", "SENTINELHUB_CLIENT_SECRET"],
            description="Processed Sentinel imagery for tactical COP tiles and statistics.",
        )

    def _token_request(self) -> str:
        cid = self._env("SENTINELHUB_CLIENT_ID")
        csec = self._env("SENTINELHUB_CLIENT_SECRET")
        if not cid or not csec:
            return ""
        body = parse.urlencode({"grant_type": "client_credentials", "client_id": cid, "client_secret": csec}).encode("utf-8")
        req = request.Request(self.config.token_url, method="POST", data=body)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with request.urlopen(req, timeout=8) as resp:
            return str(json.loads(resp.read().decode("utf-8")).get("access_token", ""))

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "catalog_search_response.json").exists()
        try:
            return bool(self._token_request())
        except Exception:
            return False

    def fetch(self, params: dict[str, Any]) -> Any:
        api = params.get("api", "catalog")
        if api == "process":
            return self.fetch_sar_imagery(params.get("aoi", "persian_gulf"), int(params.get("days_back", 3)), int(params.get("width", 512)), int(params.get("height", 512)))
        if api == "statistics":
            return self.fetch_statistics(params.get("aoi", "full_saudi"), params.get("collection", "sentinel-2-l2a"), params.get("evalscript", "ndvi"), int(params.get("months_back", 6)))
        return self.fetch_catalog(params.get("collection", "sentinel-1-grd"), params.get("bbox"), int(params.get("days_back", 7)), params.get("aoi", "persian_gulf"))

    def fetch_sar_imagery(self, aoi: str, days_back: int, width: int = 512, height: int = 512) -> dict[str, Any]:
        if self.is_airgapped:
            meta = self._read_json(self.fixture_dir / "process_metadata.json")
            return {"imagery_bytes": b"PNG_FIXTURE_BYTES", "metadata": {**meta, "aoi": aoi, "days_back": days_back, "width": width, "height": height}}
        raise RuntimeError("Online SentinelHub Process API disabled in offline-first environment")

    def fetch_statistics(self, aoi: str, collection: str, evalscript_name: str, months_back: int = 6) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "statistics_response.json")
            payload["metadata"] = {"aoi": aoi, "collection": collection, "evalscript": evalscript_name, "months_back": months_back}
            return payload
        raise RuntimeError("Online SentinelHub stats disabled in offline-first environment")

    def fetch_catalog(self, collection: str, bbox: list[float] | None, days_back: int, aoi: str | None = None) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "catalog_search_response.json")
            if bbox:
                payload["bbox"] = bbox
            if aoi:
                payload["aoi"] = aoi
            payload["collection"] = collection
            payload["days_back"] = days_back
            return payload

        token = self._token_request()
        if not token:
            raise RuntimeError("Missing SentinelHub credentials")
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days_back)
        query = {
            "collections": [collection],
            "datetime": f"{start.isoformat()}/{now.isoformat()}",
            "bbox": bbox or self.config.saudi_aois.get(aoi or "persian_gulf", self.config.saudi_aois["persian_gulf"]),
            "limit": 10,
        }
        req = request.Request(self.config.catalog_url, method="POST", data=json.dumps(query).encode("utf-8"))
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "features" in raw_data:
            observations = [self.normalizer.normalize_catalog_result(item) for item in raw_data.get("features", [])]
            return {"observations": observations, "count": len(observations)}
        if isinstance(raw_data, dict) and "imagery_bytes" in raw_data:
            return self.normalizer.normalize_process_result(raw_data["imagery_bytes"], raw_data.get("metadata", {}))
        if isinstance(raw_data, dict) and "data" in raw_data:
            return {"statistics": self.normalizer.normalize_statistics(raw_data)}
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        detail = "credentials valid" if ok else "credentials unavailable"
        if ok:
            try:
                self.fetch_catalog("sentinel-1-grd", None, 1, aoi="persian_gulf")
                detail = "catalog endpoint reachable or fixture available"
            except Exception as exc:  # pragma: no cover
                ok = False
                detail = f"catalog ping failed: {exc}"
        return {"status": "ok" if ok else "degraded", "latency": round((time.perf_counter()-start)*1000.0, 2), "detail": detail}
