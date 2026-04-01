"""Mapbox adapter with online ingestion and air-gapped cache support."""

from __future__ import annotations

import json
import math
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest, ensure_directory
from packages.providers.gis_mapbox.config import MapboxConfig
from packages.providers.gis_mapbox.normalizer import MapboxNormalizer


class MapboxAdapter(ProviderAdapter):
    provider_id = "gis-mapbox"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = MapboxConfig()
        self.normalizer = MapboxNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "gis-mapbox" / "fixtures"
        self.cache_root = ensure_directory(self.config.offline_cache_dir)
        self.mbtiles_root = ensure_directory(self.config.mbtiles_dir)

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="MAPPING_TERRAIN",
            tier="FREEMIUM",
            auth_type="api_key",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["MAPBOX_ACCESS_TOKEN"],
            description="Mapbox tactical map tiles with offline MBTiles support for field operations.",
        )

    def _token(self) -> str:
        return self._env("MAPBOX_ACCESS_TOKEN")

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return any(self.mbtiles_root.glob("*.mbtiles"))
        return bool(self._token())

    def _cache_tile_path(self, style: str, z: int, x: int, y: int, ext: str) -> Path:
        return self.cache_root / style / str(z) / str(x) / f"{y}.{ext}"

    @staticmethod
    def _lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
        lat = min(max(lat, -85.05112878), 85.05112878)
        n = 2**zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
        return xtile, ytile

    def _read_from_mbtiles(self, z: int, x: int, y: int) -> bytes | None:
        tms_y = (2**z - 1) - y
        for db_path in self.mbtiles_root.glob("*.mbtiles"):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=? LIMIT 1",
                    (z, x, tms_y),
                )
                row = cur.fetchone()
                conn.close()
                if row and row[0]:
                    return bytes(row[0])
            except Exception:
                continue
        return None

    def fetch_tile(self, z: int, x: int, y: int, style: str = "satellite") -> bytes:
        for ext in ("mvt", "jpg", "png"):
            cached = self._cache_tile_path(style, z, x, y, ext)
            if cached.exists():
                return cached.read_bytes()

        if self.is_airgapped:
            mb_tile = self._read_from_mbtiles(z, x, y)
            if mb_tile is not None:
                return mb_tile
            raise FileNotFoundError(f"No cached tile for {z}/{x}/{y} ({style})")

        token = self._token()
        if not token:
            raise RuntimeError("Missing MAPBOX access token")

        ext = "jpg" if style == "satellite" else "mvt"
        if style == "satellite":
            endpoint = f"/v4/mapbox.satellite-v9/{z}/{x}/{y}@2x.jpg"
        else:
            endpoint = f"/v4/mapbox.mapbox-streets-v8/{z}/{x}/{y}.mvt"
        url = f"{self.config.base_url}{endpoint}?access_token={parse.quote(token)}"

        with request.urlopen(url, timeout=10) as resp:
            payload = resp.read()
        out_path = self._cache_tile_path(style, z, x, y, ext)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        return payload

    def fetch_tile_range(self, bounds: dict[str, float], min_zoom: int = 0, max_zoom: int = 14, style: str = "satellite") -> dict[str, Any]:
        downloaded = 0
        total_bytes = 0
        for z in range(int(min_zoom), int(max_zoom) + 1):
            x_w, y_n = self._lonlat_to_tile(bounds["west"], bounds["north"], z)
            x_e, y_s = self._lonlat_to_tile(bounds["east"], bounds["south"], z)
            for x in range(min(x_w, x_e), max(x_w, x_e) + 1):
                for y in range(min(y_n, y_s), max(y_n, y_s) + 1):
                    try:
                        tile = self.fetch_tile(z, x, y, style=style)
                        downloaded += 1
                        total_bytes += len(tile)
                    except Exception:
                        continue
        return {
            "tiles_downloaded": downloaded,
            "total_size_mb": round(total_bytes / (1024 * 1024), 3),
            "bounds": bounds,
            "zoom_range": f"{min_zoom}-{max_zoom}",
        }

    def _load_gazetteer(self) -> list[dict[str, Any]]:
        cache_path = Path(self.config.gazetteer_cache_path)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        fixture = self._read_json(self.fixture_dir / "geocode_riyadh.json")
        return fixture.get("features", [])

    def geocode(self, query: str, country: str = "SA") -> list[dict[str, Any]]:
        del country
        if self.is_airgapped:
            q = query.lower().strip()
            results = []
            for feature in self._load_gazetteer():
                name = str(feature.get("place_name", feature.get("text", ""))).lower()
                if q in name:
                    results.append(
                        {
                            "place_name": feature.get("place_name", feature.get("text")),
                            "coordinates": feature.get("center", [None, None]),
                            "place_type": (feature.get("place_type") or [None])[0],
                            "relevance": feature.get("relevance", 1.0),
                        }
                    )
            return results

        token = self._token()
        params = parse.urlencode(
            {
                "access_token": token,
                "country": self.config.geocoding_countries,
                "language": self.config.geocoding_languages,
            }
        )
        safe_query = parse.quote(query)
        url = f"{self.config.base_url}/geocoding/v5/mapbox.places/{safe_query}.json?{params}"
        with request.urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return [
            {
                "place_name": item.get("place_name"),
                "coordinates": item.get("center", [None, None]),
                "place_type": (item.get("place_type") or [None])[0],
                "relevance": item.get("relevance", 0.0),
            }
            for item in payload.get("features", [])
        ]

    def reverse_geocode(self, lat: float, lon: float) -> dict[str, Any]:
        if self.is_airgapped:
            nearest = self.geocode("Riyadh")
            item = nearest[0] if nearest else {}
            return {
                "place_name": item.get("place_name", "Unknown"),
                "region": "Riyadh Region",
                "country": "Saudi Arabia",
                "postal_code": None,
            }

        token = self._token()
        params = parse.urlencode({"access_token": token, "language": self.config.geocoding_languages})
        url = f"{self.config.base_url}/geocoding/v5/mapbox.places/{lon},{lat}.json?{params}"
        with request.urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        features = payload.get("features", [])
        top = features[0] if features else {}
        context = top.get("context", [])
        return {
            "place_name": top.get("place_name"),
            "region": next((c.get("text") for c in context if "region" in str(c.get("id", ""))), None),
            "country": next((c.get("text") for c in context if "country" in str(c.get("id", ""))), None),
            "postal_code": next((c.get("text") for c in context if "postcode" in str(c.get("id", ""))), None),
        }

    def get_route(self, origin: tuple[float, float], destination: tuple[float, float], profile: str = "driving") -> dict[str, Any] | None:
        if self.is_airgapped:
            return {
                "route": None,
                "note": "routing unavailable in airgapped mode — use Phase 8 PathPlanner with offline elevation data",
            }

        token = self._token()
        coords = f"{origin[0]},{origin[1]};{destination[0]},{destination[1]}"
        params = parse.urlencode({"access_token": token, "geometries": "geojson"})
        url = f"{self.config.base_url}/directions/v5/mapbox/{profile}/{coords}?{params}"
        with request.urlopen(url, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        route = (payload.get("routes") or [{}])[0]
        return {
            "distance_m": route.get("distance", 0.0),
            "duration_s": route.get("duration", 0.0),
            "geometry": route.get("geometry", {}).get("coordinates", []),
            "steps": route.get("legs", [{}])[0].get("steps", []),
        }

    def fetch_static_map(self, lat: float, lon: float, zoom: int, width: int = 800, height: int = 600, style: str = "satellite_streets") -> bytes:
        if self.is_airgapped:
            return b"PNG_STATIC_MAP_FIXTURE"

        token = self._token()
        style_path = self.config.tile_styles.get(style, self.config.tile_styles[self.config.default_style])
        endpoint = f"/styles/v1/{style_path}/static/{lon},{lat},{zoom},0,0/{width}x{height}@2x"
        url = f"{self.config.base_url}{endpoint}?access_token={parse.quote(token)}"
        with request.urlopen(url, timeout=10) as resp:
            return resp.read()

    def generate_offline_pack(self, region: str = "full_saudi", max_zoom: int = 14) -> dict[str, Any]:
        bounds = self.config.saudi_tile_bounds.get(region, self.config.saudi_tile_bounds["full_saudi"])
        fetch_meta = self.fetch_tile_range(bounds, min_zoom=0, max_zoom=max_zoom, style="satellite")

        mb_path = self.mbtiles_root / f"{region}_z0_{max_zoom}.mbtiles"
        conn = sqlite3.connect(mb_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS tile_index ON tiles (zoom_level, tile_column, tile_row)")

        tile_count = 0
        source_root = self.cache_root / "satellite"
        if source_root.exists():
            for tile_path in source_root.glob("*/*/*.*"):
                z = int(tile_path.parts[-3])
                x = int(tile_path.parts[-2])
                y = int(tile_path.stem)
                tms_y = (2**z - 1) - y
                cur.execute(
                    "INSERT OR REPLACE INTO tiles(zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
                    (z, x, tms_y, tile_path.read_bytes()),
                )
                tile_count += 1

        cur.execute("INSERT OR REPLACE INTO metadata(name, value) VALUES('name', ?)", (f"s3m-{region}",))
        cur.execute("INSERT OR REPLACE INTO metadata(name, value) VALUES('format', 'jpg')")
        conn.commit()
        conn.close()

        return {
            "mbtiles_path": str(mb_path),
            "tile_count": tile_count,
            "size_mb": round(mb_path.stat().st_size / (1024 * 1024), 3) if mb_path.exists() else 0.0,
            "region": region,
            "zoom_range": f"0-{max_zoom}",
            "downloaded_tiles": fetch_meta.get("tiles_downloaded", 0),
        }

    def query_terrain_at_point(self, lat: float, lon: float) -> dict[str, Any]:
        if self.is_airgapped:
            return self._read_json(self.fixture_dir / "terrain_query.json")

        token = self._token()
        params = parse.urlencode({"access_token": token})
        url = f"{self.config.base_url}/v4/mapbox.mapbox-terrain-v2/tilequery/{lon},{lat}.json?{params}"
        with request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch(self, params: dict[str, Any]) -> Any:
        action = params.get("action", "tile")
        if action == "tile_range":
            return self.fetch_tile_range(params["bounds"], int(params.get("min_zoom", 0)), int(params.get("max_zoom", self.config.max_zoom_offline)), params.get("style", "satellite"))
        if action == "geocode":
            return self.geocode(params.get("query", "Riyadh"), params.get("country", "SA"))
        if action == "route":
            return self.get_route(params["origin"], params["destination"], params.get("profile", "driving"))
        if action == "terrain":
            return self.query_terrain_at_point(float(params["lat"]), float(params["lon"]))
        return self.fetch_tile(int(params.get("z", 0)), int(params.get("x", 0)), int(params.get("y", 0)), params.get("style", "satellite"))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and {"z", "x", "y"}.issubset(raw_data.keys()):
            return self.normalizer.normalize_tile_metadata(raw_data)
        if isinstance(raw_data, dict) and "routes" in raw_data:
            route = raw_data.get("routes", [{}])[0]
            return self.normalizer.normalize_route(route)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "cache ready" if self.is_airgapped else "token configured",
            "mode": self.mode,
        }
