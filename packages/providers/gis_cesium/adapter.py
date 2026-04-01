"""Cesium ion adapter for 3D terrain and tileset ingestion with local caching."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest, ensure_directory
from packages.providers.gis_cesium.config import CesiumConfig
from packages.providers.gis_cesium.normalizer import CesiumNormalizer
from packages.providers.gis_srtm.adapter import SRTMAdapter


class CesiumAdapter(ProviderAdapter):
    provider_id = "gis-cesium"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = CesiumConfig()
        self.normalizer = CesiumNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "gis-cesium" / "fixtures"
        self.terrain_cache = ensure_directory(self.config.terrain_cache_dir)
        self.tiles3d_cache = ensure_directory(self.config.tiles_3d_cache_dir)
        self.srtm_fallback = SRTMAdapter(mode="airgapped")

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="MAPPING_TERRAIN",
            tier="FREEMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["CESIUM_ION_TOKEN"],
            description="Cesium World Terrain and 3D tiles adapter with air-gapped cache mode.",
        )

    def _token(self) -> str:
        return self._env("CESIUM_ION_TOKEN")

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return any(self.terrain_cache.glob("*.terrain"))
        return bool(self._token())

    @staticmethod
    def _tile_name(z: int, x: int, y: int) -> str:
        return f"{z}_{x}_{y}.terrain"

    def fetch_terrain_tile(self, z: int, x: int, y: int) -> bytes:
        cache_file = self.terrain_cache / self._tile_name(z, x, y)
        if cache_file.exists():
            return cache_file.read_bytes()

        if self.is_airgapped:
            raise FileNotFoundError(f"Missing cached Cesium tile {z}/{x}/{y}")

        token = self._token()
        url = f"{self.config.assets_url}/{self.config.world_terrain_asset_id}/{z}/{x}/{y}.terrain?v=1.2.0"
        req = request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with request.urlopen(req, timeout=15) as resp:
            payload = resp.read()
        cache_file.write_bytes(payload)
        return payload

    @staticmethod
    def _lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
        lat = min(max(lat, -85.05112878), 85.05112878)
        n = 2**zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2.0 * n)
        return xtile, ytile

    def fetch_terrain_region(self, bounds: dict[str, float], max_zoom: int = 12) -> dict[str, Any]:
        x_w, y_n = self._lonlat_to_tile(bounds["west"], bounds["north"], max_zoom)
        x_e, y_s = self._lonlat_to_tile(bounds["east"], bounds["south"], max_zoom)
        tiles_cached = 0
        total_bytes = 0
        for x in range(min(x_w, x_e), max(x_w, x_e) + 1):
            for y in range(min(y_n, y_s), max(y_n, y_s) + 1):
                try:
                    payload = self.fetch_terrain_tile(max_zoom, x, y)
                    tiles_cached += 1
                    total_bytes += len(payload)
                except Exception:
                    continue
        return {"tiles_cached": tiles_cached, "size_mb": round(total_bytes / (1024 * 1024), 3), "bounds": bounds}

    def fetch_3d_tileset(self, asset_id: int) -> dict[str, Any]:
        cache_file = self.tiles3d_cache / f"{asset_id}_tileset.json"
        if self.is_airgapped:
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))
            return self._read_json(self.fixture_dir / "tileset_root.json")

        token = self._token()
        url = f"{self.config.assets_url}/{asset_id}/tileset.json"
        req = request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    def fetch_elevation_at_point(self, lat: float, lon: float) -> float:
        return float(self.srtm_fallback.get_elevation(lat, lon) or 0.0)

    def list_assets(self) -> list[dict[str, Any]]:
        if self.is_airgapped:
            return self._read_json(self.fixture_dir / "assets_list.json").get("items", [])

        token = self._token()
        req = request.Request(f"{self.config.ion_api_url}/assets", headers={"Authorization": f"Bearer {token}"})
        with request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("items", payload.get("assets", []))

    def geocode(self, query: str) -> list[dict[str, Any]]:
        if self.is_airgapped:
            return [{"name": "Riyadh", "coordinates": [46.6753, 24.7136], "source": "cesium-fixture"}] if "riyadh" in query.lower() else []

        token = self._token()
        params = parse.urlencode({"text": query})
        req = request.Request(f"{self.config.ion_api_url}/geocode?{params}", headers={"Authorization": f"Bearer {token}"})
        with request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("features", [])

    def generate_offline_terrain(self, region: str = "full_saudi", max_zoom: int = 12) -> dict[str, Any]:
        bounds = self.config.saudi_bounds.get(region, self.config.saudi_bounds["full_saudi"])
        meta = self.fetch_terrain_region(bounds, max_zoom=max_zoom)
        return {
            "cache_path": str(self.terrain_cache),
            "tile_count": meta["tiles_cached"],
            "size_mb": meta["size_mb"],
            "region": region,
        }

    def fetch(self, params: dict[str, Any]) -> Any:
        action = params.get("action", "assets")
        if action == "terrain_tile":
            return self.fetch_terrain_tile(int(params["z"]), int(params["x"]), int(params["y"]))
        if action == "terrain_region":
            return self.fetch_terrain_region(params["bounds"], int(params.get("max_zoom", 12)))
        if action == "tileset":
            return self.fetch_3d_tileset(int(params.get("asset_id", self.config.osm_buildings_asset_id)))
        if action == "elevation":
            return self.fetch_elevation_at_point(float(params["lat"]), float(params["lon"]))
        if action == "geocode":
            return self.geocode(params.get("query", "Riyadh"))
        if action == "offline":
            return self.generate_offline_terrain(params.get("region", "full_saudi"), int(params.get("max_zoom", 12)))
        return self.list_assets()

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and {"z", "x", "y"}.issubset(raw_data.keys()):
            return self.normalizer.normalize_terrain_metadata(raw_data)
        if isinstance(raw_data, dict) and "root" in raw_data:
            return self.normalizer.normalize_3d_tileset(raw_data)
        if isinstance(raw_data, list):
            return self.normalizer.normalize_asset_list(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": f"terrain_cache_tiles={len(list(self.terrain_cache.glob('*.terrain')))}",
        }
