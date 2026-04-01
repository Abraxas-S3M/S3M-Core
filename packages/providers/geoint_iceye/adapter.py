"""ICEYE SAR adapter with change detection analytics wrappers."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import ICEYEConfig
from .normalizer import ICEYENormalizer


class ICEYEAdapter(ProviderAdapter):
    provider_id = "geoint-iceye"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = ICEYEConfig()
        self.normalizer = ICEYENormalizer(self.config)
        self.fixture_dir = Path(__file__).resolve().parents[1] / "geoint-iceye" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="PREMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["ICEYE_API_KEY"],
            description="ICEYE premium SAR catalog, tasking, and analytics adapter.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "catalog_search_hormuz.json").exists()
        return bool(self._env("ICEYE_API_KEY"))

    def _load_fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def search_catalog(self, bbox: list[float], date_from: str, date_to: str, limit: int = 20) -> dict[str, Any]:
        payload = self._load_fixture("catalog_search_hormuz.json") if self.is_airgapped else {"scenes": []}
        scenes = payload.get("scenes", [])[:limit]
        return {"scenes": scenes, "count": len(scenes), "bbox": bbox, "datetime": f"{date_from}/{date_to}"}

    def submit_tasking(self, aoi: dict[str, Any], priority: str = "standard") -> dict[str, Any]:
        payload = self._load_fixture("tasking_order.json") if self.is_airgapped else {}
        payload["priority"] = priority
        payload["geometry"] = aoi
        return payload

    def run_change_detection(self, scene_before_id: str, scene_after_id: str) -> dict[str, Any]:
        payload = self._load_fixture("change_detection_vehicle_staging.json") if self.is_airgapped else {}
        payload["scene_before_id"] = scene_before_id
        payload["scene_after_id"] = scene_after_id
        return payload

    def run_flood_mapping(self, scene_id: str) -> dict[str, Any]:
        payload = self._load_fixture("flood_mapping.json") if self.is_airgapped else {}
        payload["scene_id"] = scene_id
        return payload

    def fetch(self, params: dict[str, Any]) -> Any:
        endpoint = str(params.get("endpoint", "catalog"))
        if endpoint == "tasking":
            return self.submit_tasking(params.get("aoi", {"type": "Polygon", "coordinates": [[[49.0, 26.0], [49.3, 26.0], [49.3, 26.3], [49.0, 26.3], [49.0, 26.0]]]}), str(params.get("priority", "standard")))
        if endpoint == "change_detection":
            return self.run_change_detection(str(params.get("scene_before_id", "ICEYE-GEO-20240601-001")), str(params.get("scene_after_id", "ICEYE-GEO-20240610-002")))
        if endpoint == "flood_mapping":
            return self.run_flood_mapping(str(params.get("scene_id", "ICEYE-GEO-20240610-002")))
        if endpoint == "saudi_sar":
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=int(params.get("days_back", 7)))
            return self.search_catalog([55.8, 25.8, 56.7, 26.6], start.date().isoformat(), end.date().isoformat(), int(params.get("limit", 20)))
        return self.search_catalog(
            params.get("bbox", [55.8, 25.8, 56.7, 26.6]),
            str(params.get("date_from", "2024-06-01")),
            str(params.get("date_to", "2024-06-15")),
            int(params.get("limit", 20)),
        )

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "scenes" in raw_data:
            observations = [self.normalizer.normalize_scene(scene) for scene in raw_data.get("scenes", [])]
            return {"observations": observations, "count": len(observations)}
        if isinstance(raw_data, dict) and "changes" in raw_data:
            return self.normalizer.normalize_change_detection(raw_data)
        if isinstance(raw_data, dict) and "flood_extent_km2" in raw_data:
            return self.normalizer.normalize_flood_mapping(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "fixture SAR and analytics available" if self.is_airgapped else "api key check",
        }
