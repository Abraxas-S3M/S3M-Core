"""OpenStreetMap/Overpass adapter with sovereign offline extraction support."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib import request

from packages.providers._shared import ProviderAdapter, ProviderManifest, ensure_directory
from packages.providers.gis_osm.config import OSMConfig
from packages.providers.gis_osm.normalizer import OSMNormalizer


class OSMAdapter(ProviderAdapter):
    provider_id = "gis-osm"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = OSMConfig()
        self.normalizer = OSMNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "gis-osm" / "fixtures"
        self.pbf_cache = ensure_directory(self.config.pbf_cache_dir)
        self.extract_cache = ensure_directory(self.config.extract_cache_dir)

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="MAPPING_TERRAIN",
            tier="FREE",
            auth_type="none",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=[],
            description="OSM/Overpass regional features for tactical route and infrastructure overlays.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            _ = list(self.pbf_cache.glob("*.pbf")) + list(self.extract_cache.glob("*.json"))
            return True
        return True

    @staticmethod
    def _bbox_tuple(bounds: dict[str, float]) -> tuple[float, float, float, float]:
        return (bounds["south"], bounds["west"], bounds["north"], bounds["east"])

    def _render_query(self, template: str, bounds: dict[str, float]) -> str:
        bbox = self._bbox_tuple(bounds)
        return template.format(bbox=f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}")

    def _fixture_for_query(self, overpass_ql: str) -> Path:
        q = overpass_ql.lower()
        if "military" in q:
            return self.fixture_dir / "overpass_military_saudi.json"
        if "aeroway" in q:
            return self.fixture_dir / "overpass_airports_saudi.json"
        if "bridge" in q or "tunnel" in q or "fuel" in q or "power" in q:
            return self.fixture_dir / "overpass_infrastructure.json"
        return self.fixture_dir / "overpass_roads_riyadh.json"

    def query_overpass(self, overpass_ql: str) -> dict[str, Any]:
        if self.is_airgapped:
            cached = sorted(self.extract_cache.glob("*.json"))
            if cached:
                payload = json.loads(cached[0].read_text(encoding="utf-8"))
            else:
                payload = self._read_json(self._fixture_for_query(overpass_ql))
            elements = payload.get("elements", [])
            return {"elements": elements, "count": len(elements)}

        query = f"[out:json][timeout:{self.config.timeout_seconds}];({overpass_ql});out body;>;out skel qt;"
        req = request.Request(
            self.config.overpass_url,
            method="POST",
            data=query.encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        elements = payload.get("elements", [])
        return {"elements": elements, "count": len(elements)}

    def fetch_roads(self, bounds: dict[str, float]) -> dict[str, Any]:
        query = self._render_query(self.config.military_queries["roads"], bounds)
        elements = self.query_overpass(query)["elements"]
        roads = [self.normalizer.normalize_road(el) for el in elements if el.get("tags", {}).get("highway")]
        return {"roads": roads, "count": len(roads)}

    def fetch_buildings(self, bounds: dict[str, float]) -> dict[str, Any]:
        query = self._render_query(self.config.military_queries["buildings"], bounds)
        elements = self.query_overpass(query)["elements"]
        buildings = [self.normalizer.normalize_building(el) for el in elements if "building" in el.get("tags", {})]
        return {"buildings": buildings, "count": len(buildings)}

    def fetch_military_features(self, bounds: dict[str, float]) -> dict[str, Any]:
        query = self._render_query(self.config.military_queries["military"], bounds)
        elements = [el for el in self.query_overpass(query)["elements"] if "military" in el.get("tags", {})]
        return {"military": elements, "count": len(elements)}

    def fetch_airports(self, bounds: dict[str, float]) -> dict[str, Any]:
        query = self._render_query(self.config.military_queries["airports"], bounds)
        elements = [el for el in self.query_overpass(query)["elements"] if "aeroway" in el.get("tags", {})]
        return {"airports": elements, "count": len(elements)}

    def fetch_ports(self, bounds: dict[str, float]) -> dict[str, Any]:
        query = self._render_query(self.config.military_queries["ports"], bounds)
        elements = self.query_overpass(query)["elements"]
        ports = [el for el in elements if "harbour" in el.get("tags", {}) or el.get("tags", {}).get("waterway") == "dock"]
        return {"ports": ports, "count": len(ports)}

    def fetch_infrastructure(self, bounds: dict[str, float]) -> dict[str, Any]:
        keys = ["bridges", "tunnels", "power", "fuel_stations"]
        merged: list[dict[str, Any]] = []
        for key in keys:
            query = self._render_query(self.config.military_queries[key], bounds)
            merged.extend(self.query_overpass(query)["elements"])
        return {"infrastructure": merged, "count": len(merged)}

    def fetch_region(self, region: str, feature_types: list[str] | None = None) -> dict[str, Any]:
        bounds = self.config.saudi_bounds.get(region, self.config.saudi_bounds["full_saudi"])
        requested = feature_types or ["roads", "buildings", "military", "airports", "ports", "infrastructure"]
        features_by_type: dict[str, list[dict[str, Any]]] = {}
        total = 0

        if "roads" in requested:
            roads = self.fetch_roads(bounds)["roads"]
            features_by_type["roads"] = roads
            total += len(roads)
        if "buildings" in requested:
            buildings = self.fetch_buildings(bounds)["buildings"]
            features_by_type["buildings"] = buildings
            total += len(buildings)
        if "military" in requested:
            military = self.fetch_military_features(bounds)["military"]
            features_by_type["military"] = military
            total += len(military)
        if "airports" in requested:
            airports = self.fetch_airports(bounds)["airports"]
            features_by_type["airports"] = airports
            total += len(airports)
        if "ports" in requested:
            ports = self.fetch_ports(bounds)["ports"]
            features_by_type["ports"] = ports
            total += len(ports)
        if "infrastructure" in requested:
            infra = self.fetch_infrastructure(bounds)["infrastructure"]
            features_by_type["infrastructure"] = infra
            total += len(infra)

        return {"region": region, "features_by_type": features_by_type, "total_features": total}

    def download_pbf(self, region: str = "saudi_arabia") -> dict[str, Any]:
        rel = self.config.pbf_downloads[region]
        target = self.pbf_cache / Path(rel).name
        if target.exists():
            return {"pbf_path": str(target), "size_mb": round(target.stat().st_size / (1024 * 1024), 3), "region": region}
        if self.is_airgapped:
            return {"pbf_path": str(target), "size_mb": 0.0, "region": region}
        url = f"{self.config.geofabrik_base}/{rel}"
        with request.urlopen(url, timeout=120) as resp:
            target.write_bytes(resp.read())
        return {"pbf_path": str(target), "size_mb": round(target.stat().st_size / (1024 * 1024), 3), "region": region}

    def fetch(self, params: dict[str, Any]) -> Any:
        action = params.get("action", "region")
        if action == "query":
            return self.query_overpass(params["overpass_ql"])
        if action == "roads":
            return self.fetch_roads(params["bounds"])
        if action == "buildings":
            return self.fetch_buildings(params["bounds"])
        if action == "military":
            return self.fetch_military_features(params["bounds"])
        if action == "airports":
            return self.fetch_airports(params["bounds"])
        if action == "ports":
            return self.fetch_ports(params["bounds"])
        if action == "infrastructure":
            return self.fetch_infrastructure(params["bounds"])
        if action == "pbf":
            return self.download_pbf(params.get("region", "saudi_arabia"))
        return self.fetch_region(params.get("region", "full_saudi"), params.get("feature_types"))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "elements" in raw_data:
            return self.normalizer.normalize_batch(raw_data.get("elements", []))
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = self.validate_credentials()
        return {
            "status": "ok" if ok else "degraded",
            "latency": round((time.perf_counter() - start) * 1000.0, 2),
            "detail": "overpass online" if not self.is_airgapped else "airgapped extract mode",
        }
