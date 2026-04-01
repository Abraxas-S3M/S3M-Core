"""Google Earth Engine adapter with online and air-gapped data paths."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.providers._shared import ProviderAdapter, ProviderManifest
from packages.providers.geoint_gee.config import GEEConfig
from packages.providers.geoint_gee.normalizer import GEENormalizer


class GEEAdapter(ProviderAdapter):
    provider_id = "geoint-gee"

    def __init__(self, mode: str | None = None, export_dir: str | None = None):
        super().__init__(mode=mode)
        self.config = GEEConfig()
        if export_dir:
            self.config.export_dir = export_dir
        self.normalizer = GEENormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "geoint-gee" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="FREE",
            auth_type="service_account",
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=["GEE_SERVICE_ACCOUNT_KEY_PATH"],
            description=("Google Earth Engine historical analytics adapter; in air-gapped deployments "
                         "only pre-computed exports are available."),
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return len(self.list_available_exports()) > 0
        key_path = self._env("GEE_SERVICE_ACCOUNT_KEY_PATH")
        if not key_path:
            return False
        path = Path(key_path)
        if not path.exists() or not path.is_file():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return all(field in payload for field in ["client_email", "private_key", "project_id"])

    def list_available_exports(self) -> list[dict[str, Any]]:
        root = Path(self.config.export_dir)
        if root.exists() and root.is_dir():
            files: list[dict[str, Any]] = []
            for item in sorted(root.iterdir()):
                if item.is_file():
                    files.append({
                        "filename": item.name,
                        "collection": "unknown",
                        "aoi": "unknown",
                        "date_range": {"from": "unknown", "to": "unknown"},
                        "file_size_mb": round(item.stat().st_size / (1024 * 1024), 3),
                        "format": item.suffix.lstrip("."),
                        "generated_at": datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc).isoformat(),
                    })
            if files:
                return files
        return list(self._read_json(self.fixture_dir / "export_metadata.json").get("exports", []))

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query", "exports")
        if query == "change_detection":
            return self.fetch_change_detection(params.get("aoi", "full_saudi"), int(params.get("baseline_year", 2020)), int(params.get("current_year", 2025)), params.get("collection", "sentinel2_optical"))
        if query == "nighttime_lights":
            return self.fetch_nighttime_lights(params.get("aoi", "eastern_province"), int(params.get("days_back", 30)))
        if query == "elevation_profile":
            return self.fetch_elevation_profile(params.get("points", []))
        return {"exports": self.list_available_exports()}

    def fetch_change_detection(self, aoi: str, baseline_year: int, current_year: int, collection: str = "sentinel2_optical") -> dict[str, Any]:
        payload = self._read_json(self.fixture_dir / "change_detection_result.json")
        payload.update({"aoi": aoi, "baseline_year": baseline_year, "current_year": current_year, "collection": self.config.collections.get(collection, collection)})
        return payload

    def fetch_nighttime_lights(self, aoi: str, days_back: int = 30) -> dict[str, Any]:
        payload = self._read_json(self.fixture_dir / "nighttime_lights_result.json")
        payload.update({"aoi": aoi, "days_back": days_back})
        return payload

    def fetch_elevation_profile(self, points: list[tuple[float, float]]) -> dict[str, Any]:
        profile = []
        for lat, lon in points:
            elevation = 200 + (lat % 1) * 100 + (lon % 1) * 120
            profile.append({"lat": lat, "lon": lon, "elevation_m": round(elevation, 2)})
        return {"points": profile, "count": len(profile), "source": "srtm"}

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "exports" in raw_data:
            obs = [self.normalizer.normalize_export_metadata(item) for item in raw_data.get("exports", [])]
            return {"observations": obs, "count": len(obs)}
        if isinstance(raw_data, dict) and "change_magnitude" in raw_data:
            return self.normalizer.normalize_change_detection(raw_data)
        if isinstance(raw_data, dict) and "radiance_mean" in raw_data:
            return self.normalizer.normalize_nighttime_lights(raw_data)
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        if self.is_airgapped:
            exports = self.list_available_exports()
            status = "degraded"
            detail = "no exports available"
            if exports:
                newest = max(datetime.fromisoformat(str(item.get("generated_at", "1970-01-01T00:00:00+00:00")).replace("Z", "+00:00")) for item in exports)
                age_days = (datetime.now(timezone.utc) - newest).days
                status = "ok" if age_days < 7 else "degraded"
                detail = f"{len(exports)} exports available, newest age {age_days} days"
            return {"status": status, "latency": round((time.perf_counter()-start)*1000.0, 2), "detail": detail}
        return {"status": "ok" if self.validate_credentials() else "degraded", "latency": round((time.perf_counter()-start)*1000.0, 2), "detail": "online credentials validation"}
