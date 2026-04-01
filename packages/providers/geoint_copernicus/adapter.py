"""Minimal Copernicus adapter used by GEOINT merged pipeline tests."""

from __future__ import annotations

from typing import Any

from packages.providers._shared import GEOINT_SAUDI_AOIS, GeoPoint, NormalizedGeoObservation, ProviderAdapter, ProviderManifest, Provenance


class CopernicusAdapter(ProviderAdapter):
    provider_id = "geoint-copernicus"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="FREE",
            auth_type="oauth2",
            rate_limit_rpm=30,
            description="Baseline Copernicus catalog feed for SAR scenes.",
        )

    def validate_credentials(self) -> bool:
        return True

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        aoi = params.get("aoi", "persian_gulf")
        bbox = GEOINT_SAUDI_AOIS.get(aoi, GEOINT_SAUDI_AOIS["persian_gulf"])
        return {
            "features": [
                {
                    "id": "S1A_DUPLICATE_PASS_001",
                    "datetime": "2026-03-25T09:20:00Z",
                    "satellite": "Sentinel-1A",
                    "observation_type": "sar",
                    "collection": "sentinel-1-grd",
                    # Tactical overlap fixture: intentionally mirrors SentinelHub catalog scene.
                    "lat": 26.95,
                    "lon": 49.10,
                },
                {
                    "id": "S1A_UNIQUE_PASS_002",
                    "datetime": "2026-03-24T08:10:00Z",
                    "satellite": "Sentinel-1A",
                    "observation_type": "sar",
                    "collection": "sentinel-1-grd",
                    "lat": bbox[1] + 0.8,
                    "lon": bbox[0] + 0.9,
                },
            ],
            "aoi": aoi,
        }

    def normalize(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        observations: list[NormalizedGeoObservation] = []
        for f in raw_data.get("features", []):
            observations.append(
                NormalizedGeoObservation(
                    observation_id=f["id"],
                    timestamp=f["datetime"],
                    provider_id=self.provider_id,
                    observation_type=f["observation_type"],
                    satellite=f["satellite"],
                    collection=f["collection"],
                    geo_point=GeoPoint(lat=float(f["lat"]), lon=float(f["lon"])),
                    resolution_m=10.0,
                    tags=["copernicus", "sar", raw_data.get("aoi", "unknown")],
                    provenance=Provenance(provider_id=self.provider_id, source="copernicus-catalog", confidence=0.8),
                )
            )
        return {"observations": observations}

    def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "latency": 0.1, "detail": "copernicus fixture available"}
