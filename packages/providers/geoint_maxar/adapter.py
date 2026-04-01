"""Maxar SecureWatch/eAPI adapter using fixture-backed offline paths."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import MaxarConfig
from .normalizer import MaxarNormalizer


class MaxarAdapter(ProviderAdapter):
    provider_id = "geoint-maxar"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = MaxarConfig()
        self.normalizer = MaxarNormalizer(self.config)
        self.fixture_dir = Path(__file__).resolve().parents[1] / "geoint-maxar" / "fixtures"
        self.cache_dir = Path("data/integrations/geoint-maxar")

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="PREMIUM",
            auth_type="oauth2",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["MAXAR_API_KEY", "MAXAR_SECRET_KEY"],
            description="Maxar SecureWatch/eAPI high-resolution defense imagery and 3D terrain feed.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "catalog_search_wv03.json").exists()
        return bool(self._env("MAXAR_API_KEY") and self._env("MAXAR_SECRET_KEY"))

    def _load_fixture(self, name: str) -> dict[str, Any]:
        return self._read_json(self.fixture_dir / name)

    def fetch(self, params: dict[str, Any]) -> Any:
        endpoint = str(params.get("endpoint", "catalog")).lower()
        if endpoint == "tile":
            return self.fetch_imagery_tile(
                str(params.get("image_id", "maxar-wv03-20240610-001")),
                int(params.get("z", 12)),
                int(params.get("x", 2345)),
                int(params.get("y", 1623)),
                str(params.get("style", "default")),
            )
        if endpoint == "tasking":
            return self.submit_tasking(
                str(params.get("aoi_wkt", "POLYGON((56.0 26.0,56.4 26.0,56.4 26.3,56.0 26.3,56.0 26.0))")),
                str(params.get("sensor", "WV03")),
                str(params.get("priority", "standard")),
                params.get("start_date"),
                params.get("end_date"),
            )
        if endpoint == "terrain":
            return self.fetch_3d_terrain(int(params.get("z", 11)), int(params.get("x", 1234)), int(params.get("y", 987)))
        return self.search_catalog(
            params.get("bbox", self.config.saudi_aois["persian_gulf"]),
            str(params.get("date_from", (datetime.now(timezone.utc) - timedelta(days=14)).date())),
            str(params.get("date_to", datetime.now(timezone.utc).date())),
            params.get("satellites"),
            int(params.get("max_cloud", 20)),
            int(params.get("limit", 20)),
        )

    def search_catalog(
        self,
        bbox: list[float],
        date_from: str,
        date_to: str,
        satellites: list[str] | None = None,
        max_cloud: int = 20,
        limit: int = 20,
    ) -> dict[str, Any]:
        payload = self._load_fixture("catalog_search_wv03.json") if self.is_airgapped else {"images": [], "count": 0}
        images = payload.get("images", [])
        sat_filter = {s.lower() for s in satellites} if satellites else set()
        filtered = []
        for item in images:
            sat = str(item.get("satellite", "")).lower()
            cloud = float(item.get("cloud_cover", 0.0))
            if sat_filter and sat not in sat_filter:
                continue
            if cloud > max_cloud:
                continue
            filtered.append(item)
        return {
            "images": filtered[:limit],
            "count": len(filtered[:limit]),
            "bbox": bbox,
            "datetime": f"{date_from}/{date_to}",
        }

    def fetch_imagery_tile(self, image_id: str, z: int, x: int, y: int, style: str = "default") -> bytes:
        # Tactical context: tile caching preserves mission imagery in disconnected operations.
        if self.is_airgapped:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            tile_path = self.cache_dir / f"{image_id}_{z}_{x}_{y}_{style}.tile"
            if tile_path.exists():
                return tile_path.read_bytes()
            data = f"MAXAR_TILE::{image_id}::{z}/{x}/{y}::{style}".encode("utf-8")
            tile_path.write_bytes(data)
            return data
        return f"MAXAR_ONLINE_TILE::{image_id}::{z}/{x}/{y}::{style}".encode("utf-8")

    def submit_tasking(
        self,
        aoi_wkt: str,
        sensor: str = "WV03",
        priority: str = "standard",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        payload = self._load_fixture("tasking_order.json") if self.is_airgapped else {}
        if not payload:
            now = datetime.now(timezone.utc)
            payload = {
                "order_id": "MAXAR-ORDER-ONLINE",
                "estimated_collection_date": (now + timedelta(days=2)).isoformat(),
                "sensor": sensor,
                "status": "submitted",
                "priority": priority,
            }
        payload["sensor"] = sensor
        payload["priority"] = priority
        payload["aoi_wkt"] = aoi_wkt
        payload["start_date"] = start_date
        payload["end_date"] = end_date
        return payload

    def fetch_3d_terrain(self, z: int, x: int, y: int) -> bytes:
        metadata = self._load_fixture("3d_terrain_metadata.json")
        content = f"MAXAR_3D::{z}/{x}/{y}::{metadata.get('tile_id', 'unknown')}".encode("utf-8")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"terrain_{z}_{x}_{y}.terrain").write_bytes(content)
        return content

    def search_saudi_archive(self, aoi: str = "persian_gulf", days_back: int = 30, satellite: str = "wv03") -> dict[str, Any]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)
        return self.search_catalog(
            self.config.saudi_aois.get(aoi, self.config.saudi_aois["persian_gulf"]),
            start.date().isoformat(),
            end.date().isoformat(),
            satellites=[satellite],
            max_cloud=25,
            limit=20,
        )

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "images" in raw_data:
            observations = [self.normalizer.normalize_catalog_result(img) for img in raw_data.get("images", [])]
            return {"observations": observations, "count": len(observations)}
        if isinstance(raw_data, dict) and "order_id" in raw_data:
            return self.normalizer.normalize_tasking_order(raw_data)
        if isinstance(raw_data, dict) and raw_data.get("layer_type") == "terrain":
            return self.normalizer.normalize_3d_terrain(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        detail = "fixture and cache available" if self.is_airgapped else "credential check"
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": detail,
        }
