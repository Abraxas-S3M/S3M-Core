"""NASA Earthdata adapter for FIRMS active fires and CMR granules."""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest
from packages.providers.geoint_nasa_earthdata.config import NASAEarthdataConfig
from packages.providers.geoint_nasa_earthdata.normalizer import NASAEarthdataNormalizer


class NASAEarthdataAdapter(ProviderAdapter):
    provider_id = "geoint-nasa-earthdata"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = NASAEarthdataConfig()
        self.normalizer = NASAEarthdataNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "geoint-nasa-earthdata" / "fixtures"

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            category="GEOINT",
            tier="FREE",
            auth_type="api_key",
            rate_limit_rpm=self.config.firms_rate_limit_rpm,
            required_env_vars=["NASA_FIRMS_MAP_KEY"],
            optional_env_vars=["NASA_EARTHDATA_TOKEN"],
            description="NASA FIRMS thermal hotspot feed for strike and infrastructure verification.",
        )

    def validate_credentials(self) -> bool:
        if self.is_airgapped:
            return (self.fixture_dir / "firms_viirs_saudi_response.csv").exists()
        return bool(self._env("NASA_FIRMS_MAP_KEY"))

    def _parse_firms_csv(self, csv_payload: str, instrument: str) -> list[dict[str, Any]]:
        reader = csv.DictReader(io.StringIO(csv_payload))
        out: list[dict[str, Any]] = []
        for idx, row in enumerate(reader, start=1):
            acq_date = row.get("acq_date", "1970-01-01")
            acq_time = str(row.get("acq_time", "0000")).zfill(4)
            ts = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
            out.append({
                "id": f"firms-{idx}",
                "latitude": float(row.get("latitude", 0.0)),
                "longitude": float(row.get("longitude", 0.0)),
                "bright_ti4": float(row.get("bright_ti4", 0.0)),
                "scan": float(row.get("scan", 0.0)),
                "track": float(row.get("track", 0.0)),
                "acq_date": acq_date,
                "acq_time": acq_time,
                "acq_datetime": ts.isoformat(),
                "satellite": row.get("satellite", "N"),
                "confidence": str(row.get("confidence", "low")).lower(),
                "version": row.get("version", ""),
                "bright_ti5": float(row.get("bright_ti5", 0.0)),
                "frp": float(row.get("frp", 0.0)),
                "daynight": row.get("daynight", "U"),
                "instrument": instrument,
            })
        return out

    def fetch(self, params: dict[str, Any]) -> Any:
        source = params.get("source", "firms")
        if source == "cmr":
            return self.fetch_cmr_granules(params["collection_id"], params.get("bbox", self.config.saudi_bbox["full_saudi"]), params.get("date_range", ("2026-01-01", "2026-01-31")), int(params.get("max_results", 20)))
        if params.get("country_code"):
            return self.fetch_fires_by_country(params.get("country_code", "SAU"), int(params.get("days", 1)))
        if params.get("bbox") and all(k in params for k in ["west", "south", "east", "north"]):
            return self.fetch_fires_bbox(float(params["west"]), float(params["south"]), float(params["east"]), float(params["north"]), int(params.get("days", 1)))
        return self.fetch_active_fires(params.get("aoi", "full_saudi"), int(params.get("days", 1)), params.get("instrument", self.config.firms_default_instrument))

    def fetch_active_fires(self, aoi: str = "full_saudi", days: int = 1, instrument: str = "VIIRS_SNPP_NRT") -> dict[str, Any]:
        w, s, e, n = self.config.saudi_bbox.get(aoi, self.config.saudi_bbox["full_saudi"])
        return self.fetch_fires_bbox(w, s, e, n, days, instrument)

    def fetch_fires_by_country(self, country_code: str = "SAU", days: int = 1, instrument: str = "VIIRS_SNPP_NRT") -> dict[str, Any]:
        if self.is_airgapped:
            csv_payload = self._read_text(self.fixture_dir / "firms_viirs_saudi_response.csv")
        else:
            key = self._env("NASA_FIRMS_MAP_KEY")
            if not key:
                raise RuntimeError("Missing NASA_FIRMS_MAP_KEY")
            url = f"{self.config.firms_base_url}/country/csv/{key}/{instrument}/{country_code}/{days}"
            with request.urlopen(url, timeout=10) as resp:
                csv_payload = resp.read().decode("utf-8")
        fires = self._parse_firms_csv(csv_payload, instrument)
        filtered = self.normalizer.filter_by_confidence(fires, self.config.fire_confidence_threshold)
        return {"fires": filtered, "count": len(filtered), "instrument": instrument, "period_days": days, "country_code": country_code}

    def fetch_fires_bbox(self, west: float, south: float, east: float, north: float, days: int = 1, instrument: str = "VIIRS_SNPP_NRT") -> dict[str, Any]:
        if self.is_airgapped:
            csv_payload = self._read_text(self.fixture_dir / "firms_viirs_saudi_response.csv")
        else:
            key = self._env("NASA_FIRMS_MAP_KEY")
            if not key:
                raise RuntimeError("Missing NASA_FIRMS_MAP_KEY")
            area = f"{west},{south},{east},{north}"
            url = f"{self.config.firms_base_url}/area/csv/{key}/{instrument}/{area}/{days}"
            with request.urlopen(url, timeout=10) as resp:
                csv_payload = resp.read().decode("utf-8")
        fires = self._parse_firms_csv(csv_payload, instrument)
        filtered = self.normalizer.filter_by_confidence(fires, self.config.fire_confidence_threshold)
        return {"fires": filtered, "count": len(filtered), "instrument": instrument, "period_days": days, "bbox": [west, south, east, north]}

    def fetch_cmr_granules(self, collection_id: str, bbox: list[float], date_range: tuple[str, str], max_results: int = 20) -> dict[str, Any]:
        if self.is_airgapped:
            payload = self._read_json(self.fixture_dir / "cmr_search_response.json")
            payload["query"] = {"collection_concept_id": collection_id, "bounding_box": bbox, "temporal": date_range, "page_size": max_results}
            return payload
        query = parse.urlencode({
            "collection_concept_id": collection_id,
            "bounding_box": ",".join(str(v) for v in bbox),
            "temporal": f"{date_range[0]},{date_range[1]}",
            "page_size": max_results,
        })
        with request.urlopen(f"{self.config.cmr_base_url}/granules.json?{query}", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "fires" in raw_data:
            obs = self.normalizer.normalize_fires_batch(raw_data.get("fires", []))
            return {"observations": obs, "count": len(obs)}
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            data = self.fetch_fires_by_country("SAU", 1)
            status = "ok"
            detail = f"fetched {data.get('count', 0)} records"
        except Exception as exc:  # pragma: no cover
            status = "degraded"
            detail = str(exc)
        return {"status": status, "latency": round((time.perf_counter()-start)*1000.0, 2), "detail": detail}
