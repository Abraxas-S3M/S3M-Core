"""Shared GEOINT ingestion pipeline spanning all GEOINT foundation providers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from packages.providers._shared import (
    BatchIngestionRunner,
    ChainedEnrichmentPipeline,
    HashBasedDeduplicator,
    ProviderRegistry,
    ensure_directory,
    parse_datetime,
)


class GEOINTIngestionPipeline:
    def __init__(self) -> None:
        self.registry = ProviderRegistry()
        self.registry.register_defaults()
        self.batch_runner = BatchIngestionRunner()
        self.deduplicator = HashBasedDeduplicator()
        self.enrichment = ChainedEnrichmentPipeline()

        # Tactical context: mark mission-critical sensor types for downstream alerting.
        self.enrichment.add_step(self._attach_tactical_priority)

    def _attach_tactical_priority(self, observation: dict[str, Any]) -> dict[str, Any]:
        tags = observation.setdefault("tags", [])
        if observation.get("observation_type") in {"sar", "thermal", "nighttime_radiance"} and "tactical_priority" not in tags:
            tags.append("tactical_priority")
        return observation

    def _normalize_output_to_dicts(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and "observations" in payload:
            observations = payload["observations"]
        elif isinstance(payload, list):
            observations = payload
        else:
            observations = []

        out: list[dict[str, Any]] = []
        for item in observations:
            out.append(item.to_dict() if hasattr(item, "to_dict") else dict(item))
        return out

    def _store_merged(self, aoi: str, observations: list[dict[str, Any]]) -> str:
        output_dir = ensure_directory("data/integrations/geoint-merged/")
        output_path = output_dir / f"geoint_{aoi}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        output_path.write_text(json.dumps({"aoi": aoi, "observations": observations}, indent=2), encoding="utf-8")
        return str(output_path)

    def ingest_all(self, aoi: str = "persian_gulf", days_back: int = 7) -> dict[str, Any]:
        tasks = {
            "geoint-copernicus": lambda: self.registry.get("geoint-copernicus", "airgapped").fetch_and_normalize({"aoi": aoi, "days_back": days_back}),
            "geoint-sentinelhub": lambda: self.registry.get("geoint-sentinelhub", "airgapped").fetch_and_normalize({"api": "catalog", "collection": "sentinel-1-grd", "aoi": aoi, "days_back": days_back}),
            "geoint-nasa-earthdata": lambda: self.registry.get("geoint-nasa-earthdata", "airgapped").fetch_and_normalize({"aoi": "full_saudi", "days": min(days_back, 3)}),
            "geoint-gee": lambda: self.registry.get("geoint-gee", "airgapped").fetch_and_normalize({"query": "exports", "aoi": aoi}),
        }
        results = self.batch_runner.run(tasks)

        merged: list[dict[str, Any]] = []
        by_provider: dict[str, int] = {}
        for provider_id in ["geoint-copernicus", "geoint-sentinelhub", "geoint-nasa-earthdata", "geoint-gee"]:
            obs = self._normalize_output_to_dicts(results.get(provider_id, {}).get("data", {}))
            by_provider[provider_id] = len(obs)
            merged.extend(obs)

        deduped, removed = self.deduplicator.deduplicate(merged)
        deduped.sort(key=lambda item: parse_datetime(item.get("timestamp", "")).timestamp(), reverse=True)
        deduped = self.enrichment.run(deduped)
        self._store_merged(aoi, deduped)

        return {
            "total_observations": len(deduped),
            "by_provider": by_provider,
            "deduplicated": removed,
            "aoi": aoi,
        }

    def ingest_sar_maritime(self, aoi: str = "persian_gulf", days_back: int = 3) -> dict[str, Any]:
        c = self.registry.get("geoint-copernicus", "airgapped").fetch_and_normalize({"aoi": aoi, "days_back": days_back})
        s = self.registry.get("geoint-sentinelhub", "airgapped").fetch_and_normalize({"api": "catalog", "collection": "sentinel-1-grd", "aoi": aoi, "days_back": days_back})
        combined = self._normalize_output_to_dicts(c) + self._normalize_output_to_dicts(s)
        sar_only = [item for item in combined if item.get("observation_type") == "sar"]
        return {"count": len(sar_only), "observations": sar_only, "aoi": aoi}

    def _distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        dlat = (lat2 - lat1) * 111.0
        dlon = (lon2 - lon1) * 111.0
        return (dlat**2 + dlon**2) ** 0.5

    def ingest_fires(self, region: str = "full_saudi", days: int = 1) -> dict[str, Any]:
        payload = self.registry.get("geoint-nasa-earthdata", "airgapped").fetch_and_normalize({"aoi": region, "days": days})
        observations = self._normalize_output_to_dicts(payload)

        infra = [
            {"name": "Jubail Industrial Zone", "lat": 26.96, "lon": 49.67},
            {"name": "Ghawar Oil Field", "lat": 25.4, "lon": 49.5},
            {"name": "Dhahran Air Base", "lat": 26.3, "lon": 50.1},
        ]

        for obs in observations:
            gp = obs.get("geo_point", {})
            nearest_name = None
            nearest_distance = 1e9
            near_asset = False
            for item in infra:
                distance = self._distance_km(float(gp.get("lat", 0.0)), float(gp.get("lon", 0.0)), item["lat"], item["lon"])
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_name = item["name"]
                if distance <= 25.0:
                    near_asset = True
            obs.setdefault("metadata", {})["proximity_to_infrastructure"] = near_asset
            obs["metadata"]["nearest_infrastructure"] = nearest_name
            obs["metadata"]["nearest_infrastructure_km"] = round(nearest_distance, 2)

        thermal = [item for item in observations if item.get("observation_type") == "thermal"]
        return {"count": len(thermal), "observations": thermal, "region": region}

    def get_coverage_report(self, aoi: str, days_back: int = 30) -> dict[str, Any]:
        report: dict[str, Any] = {"aoi": aoi, "days_back": days_back, "providers": {}, "gaps": []}
        for provider_id in self.registry.list_provider_ids():
            provider = self.registry.get(provider_id, "airgapped")
            if provider_id == "geoint-sentinelhub":
                payload = provider.fetch_and_normalize({"api": "catalog", "aoi": aoi, "days_back": days_back})
            elif provider_id == "geoint-nasa-earthdata":
                payload = provider.fetch_and_normalize({"aoi": "full_saudi", "days": min(days_back, 3)})
            else:
                payload = provider.fetch_and_normalize({"aoi": aoi, "days_back": days_back})

            obs = self._normalize_output_to_dicts(payload)
            report["providers"][provider_id] = {
                "count": len(obs),
                "latest_observation": obs[0]["timestamp"] if obs else None,
                "has_data": bool(obs),
            }
            if not obs:
                report["gaps"].append(provider_id)
        return report

    def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "providers": {pid: self.registry.get(pid, "airgapped").health_check() for pid in self.registry.list_provider_ids()}}
