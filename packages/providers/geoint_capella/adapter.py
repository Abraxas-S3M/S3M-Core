"""Capella SAR adapter with fixture-backed premium workflows."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import CapellaConfig
from .normalizer import CapellaNormalizer


class CapellaAdapter(ProviderAdapter):
    provider_id = "geoint-capella"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = CapellaConfig()
        self.normalizer = CapellaNormalizer(self.config)
        self.fixture_dir = Path(__file__).resolve().parents[1] / "geoint-capella" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="PREMIUM",
            auth_type="oauth2",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["CAPELLA_CLIENT_ID", "CAPELLA_CLIENT_SECRET"],
            description="Capella sub-25cm X-band SAR adapter for all-weather tactical surveillance.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "catalog_search_hormuz.json").exists()
        return bool(self._env("CAPELLA_CLIENT_ID") and self._env("CAPELLA_CLIENT_SECRET"))

    def _load_fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def search_catalog(self, bbox: list[float], date_from: str, date_to: str, product_type: str = "GEO", limit: int = 20) -> dict[str, Any]:
        payload = self._load_fixture("catalog_search_hormuz.json") if self.is_airgapped else {"scenes": []}
        scenes = [scene for scene in payload.get("scenes", []) if str(scene.get("product_type", "GEO")) == product_type]
        scenes = scenes[:limit]
        return {"scenes": scenes, "count": len(scenes), "bbox": bbox, "datetime": f"{date_from}/{date_to}"}

    def submit_tasking(self, aoi: dict[str, Any], collection_type: str = "spotlight", window_hours: int = 72) -> dict[str, Any]:
        payload = self._load_fixture("tasking_spotlight.json") if self.is_airgapped else {}
        payload["collection_type"] = collection_type
        payload["window_hours"] = window_hours
        payload["geometry"] = aoi
        return payload

    def search_saudi_sar(self, aoi: str = "strait_of_hormuz", days_back: int = 7) -> dict[str, Any]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)
        return self.search_catalog(
            self.config.saudi_aois.get(aoi, self.config.saudi_aois["strait_of_hormuz"]),
            start.date().isoformat(),
            end.date().isoformat(),
            product_type="GEO",
            limit=20,
        )

    def fetch(self, params: dict[str, Any]) -> Any:
        endpoint = str(params.get("endpoint", "catalog"))
        if endpoint == "tasking":
            return self.submit_tasking(
                params.get("aoi", {"type": "Polygon", "coordinates": [[[56.0, 26.0], [56.4, 26.0], [56.4, 26.3], [56.0, 26.3], [56.0, 26.0]]]}),
                str(params.get("collection_type", "spotlight")),
                int(params.get("window_hours", 72)),
            )
        if endpoint == "saudi_sar":
            return self.search_saudi_sar(str(params.get("aoi", "strait_of_hormuz")), int(params.get("days_back", 7)))
        return self.search_catalog(
            params.get("bbox", self.config.saudi_aois["strait_of_hormuz"]),
            str(params.get("date_from", "2024-06-01")),
            str(params.get("date_to", "2024-06-15")),
            str(params.get("product_type", "GEO")),
            int(params.get("limit", 20)),
        )

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "scenes" in raw_data:
            observations = [self.normalizer.normalize_scene(scene) for scene in raw_data.get("scenes", [])]
            return {"observations": observations, "count": len(observations)}
        if isinstance(raw_data, dict) and ("task_id" in raw_data or "collection_type" in raw_data):
            return self.normalizer.normalize_tasking(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "fixture-based SAR search" if self.is_airgapped else "oauth credential check",
        }
