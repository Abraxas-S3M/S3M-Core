"""Planet adapter using fixture-backed premium provider shell."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import PlanetConfig
from .normalizer import PlanetNormalizer


class PlanetAdapter(ProviderAdapter):
    provider_id = "geoint-planet"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = PlanetConfig()
        self.normalizer = PlanetNormalizer(self.config)
        self.fixture_dir = Path(__file__).resolve().parents[1] / "geoint-planet" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="PREMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["PLANET_API_KEY"],
            description="Planet premium daily coverage and tasking adapter for tactical monitoring.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "search_psscene_gulf.json").exists()
        return bool(self._env("PLANET_API_KEY"))

    def _load_fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def _build_search_filter(self, aoi: dict[str, Any], date_from: str, date_to: str, max_cloud: float) -> dict[str, Any]:
        return {
            "type": "AndFilter",
            "config": [
                {"type": "GeometryFilter", "field_name": "geometry", "config": aoi},
                {"type": "DateRangeFilter", "field_name": "acquired", "config": {"gte": date_from, "lte": date_to}},
                {"type": "RangeFilter", "field_name": "cloud_cover", "config": {"lte": max_cloud}},
            ],
        }

    def search(
        self,
        aoi: dict[str, Any],
        date_from: str,
        date_to: str,
        item_type: str = "PSScene",
        max_cloud: float = 0.2,
        limit: int = 50,
    ) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._load_fixture("search_psscene_gulf.json" if item_type == "PSScene" else "search_skysat_hormuz.json")
            scenes = payload.get("scenes", [])[:limit]
            return {
                "scenes": scenes,
                "count": len(scenes),
                "item_type": item_type,
                "filter": self._build_search_filter(aoi, date_from, date_to, max_cloud),
            }
        return {"scenes": [], "count": 0, "item_type": item_type, "filter": self._build_search_filter(aoi, date_from, date_to, max_cloud)}

    def submit_order(self, item_ids: list[str], item_type: str, product_bundle: str = "analytic_udm2") -> dict[str, Any]:
        payload = self._load_fixture("order_confirmation.json") if self.is_airgapped else {}
        payload["item_ids"] = item_ids
        payload["item_type"] = item_type
        payload["product_bundle"] = product_bundle
        return payload

    def submit_tasking(self, aoi: dict[str, Any], start_time: str, end_time: str, satellite: str = "SkySat-1") -> dict[str, Any]:
        return {
            "tasking_id": "PLANET-TASK-20240615-001",
            "satellite": satellite,
            "window_start": start_time,
            "window_end": end_time,
            "status": "submitted",
            "geometry": aoi,
        }

    def get_basemap_mosaic(self, name_contains: str = "global_monthly") -> dict[str, Any]:
        payload = self._load_fixture("basemap_mosaic.json") if self.is_airgapped else {}
        payload["query"] = name_contains
        return payload

    def search_daily_coverage(self, aoi: str = "persian_gulf", days_back: int = 7) -> dict[str, Any]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)
        bbox = self.config.saudi_aois.get(aoi, self.config.saudi_aois["persian_gulf"])
        polygon = {
            "type": "Polygon",
            "coordinates": [[[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]]]],
        }
        result = self.search(polygon, start.isoformat(), end.isoformat(), item_type="PSScene", max_cloud=0.3, limit=100)
        days_present = {str(scene.get("acquired", ""))[:10] for scene in result.get("scenes", [])}
        return {
            "aoi": aoi,
            "days_back": days_back,
            "days_with_coverage": sorted(d for d in days_present if d),
            "daily_revisit_expected": True,
            "scene_count": result.get("count", 0),
        }

    def fetch(self, params: dict[str, Any]) -> Any:
        endpoint = str(params.get("endpoint", "search"))
        if endpoint == "order":
            return self.submit_order(
                list(params.get("item_ids", ["PSScene-001"])),
                str(params.get("item_type", "PSScene")),
                str(params.get("product_bundle", "analytic_udm2")),
            )
        if endpoint == "tasking":
            return self.submit_tasking(
                params.get("aoi", {"type": "Polygon", "coordinates": [[[56.0, 26.0], [56.4, 26.0], [56.4, 26.3], [56.0, 26.3], [56.0, 26.0]]]}),
                str(params.get("start_time", datetime.now(timezone.utc).isoformat())),
                str(params.get("end_time", (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat())),
                str(params.get("satellite", "SkySat-1")),
            )
        if endpoint == "basemap":
            return self.get_basemap_mosaic(str(params.get("name_contains", "global_monthly")))
        if endpoint == "daily_coverage":
            return self.search_daily_coverage(str(params.get("aoi", "persian_gulf")), int(params.get("days_back", 7)))
        return self.search(
            params.get("aoi", {"type": "Polygon", "coordinates": [[[46.0, 24.0], [50.0, 24.0], [50.0, 28.0], [46.0, 28.0], [46.0, 24.0]]]}),
            str(params.get("date_from", "2024-06-01T00:00:00Z")),
            str(params.get("date_to", "2024-06-15T00:00:00Z")),
            str(params.get("item_type", "PSScene")),
            float(params.get("max_cloud", 0.2)),
            int(params.get("limit", 50)),
        )

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "scenes" in raw_data:
            observations = [self.normalizer.normalize_scene(scene) for scene in raw_data.get("scenes", [])]
            return {"observations": observations, "count": len(observations)}
        if isinstance(raw_data, dict) and ("order_id" in raw_data or "id" in raw_data):
            return self.normalizer.normalize_order(raw_data)
        if isinstance(raw_data, dict) and "tile_url_template" in raw_data:
            return self.normalizer.normalize_basemap(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "fixture catalog reachable" if self.is_airgapped else "api key check",
        }
