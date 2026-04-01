"""Saudi NDMC adapter supporting hybrid API and file-based ingestion."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

from packages.providers._shared import ProviderAdapter, ProviderManifest

from .config import SAUDI_AIRPORTS, SaudiNDMCConfig
from .normalizer import SaudiNDMCNormalizer


class SaudiNDMCAdapter(ProviderAdapter):
    provider_id = "weather-saudi-ndmc"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.config = SaudiNDMCConfig()
        self.normalizer = SaudiNDMCNormalizer()
        self.fixture_dir = Path(__file__).resolve().parents[1] / "weather-saudi-ndmc" / "fixtures"
        self.incoming_dir = Path(self.config.incoming_dir)

    def get_manifest(self) -> ProviderManifest:
        auth = "api_key" if self._env("NDMC_API_URL") and self._env("NDMC_API_KEY") else "none"
        return ProviderManifest(
            provider_id=self.provider_id,
            category="WEATHER_ENVIRONMENT",
            tier="GOVERNMENT",
            auth_type=auth,
            rate_limit_rpm=self.config.rate_limit_rpm,
            required_env_vars=[],
            optional_env_vars=["NDMC_API_KEY", "NDMC_API_URL"],
            description="Saudi sovereign weather authority adapter with METAR + official alert ingestion.",
        )

    def _api_enabled(self) -> bool:
        return bool(self._env("NDMC_API_URL") and self._env("NDMC_API_KEY")) and not self.is_airgapped

    def _request_json(self, endpoint: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        base = self._env("NDMC_API_URL")
        token = self._env("NDMC_API_KEY")
        if not base or not token:
            raise RuntimeError("NDMC API not configured")
        url = f"{base.rstrip('/')}/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{parse.urlencode(query)}"
        req = request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {token}")
        with request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def validate_credentials(self) -> bool:
        if self._api_enabled():
            try:
                self._request_json("health")
                return True
            except Exception:
                return False
        if self.is_airgapped:
            return (self.fixture_dir / "ndmc_alerts.json").exists()
        return self.incoming_dir.exists() and any(self.incoming_dir.iterdir())

    def _latest_json_from_dir(self) -> dict[str, Any]:
        if self.incoming_dir.exists():
            json_files = sorted(self.incoming_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if json_files:
                return json.loads(json_files[0].read_text(encoding="utf-8"))
        return self._read_json(self.fixture_dir / "incoming_report.json")

    def fetch_alerts(self) -> dict[str, Any]:
        if self._api_enabled():
            payload = self._request_json("alerts/current")
            alerts = payload.get("alerts", [])
            return {"alerts": alerts, "count": len(alerts), "source": "api"}
        payload = self._latest_json_from_dir()
        alerts = payload.get("alerts")
        if alerts is None:
            alerts = self._read_json(self.fixture_dir / "ndmc_alerts.json").get("alerts", [])
        return {"alerts": alerts, "count": len(alerts), "source": "file"}

    def _load_metar_records(self) -> dict[str, str]:
        if self._api_enabled():
            payload = self._request_json("metar/all")
            return {str(k): str(v) for k, v in payload.get("metar", {}).items()}
        incoming = self._latest_json_from_dir()
        if "metar" in incoming and isinstance(incoming["metar"], dict):
            return {str(k): str(v) for k, v in incoming["metar"].items()}
        fixture = self._read_json(self.fixture_dir / "metar_all_airports.json")
        return {str(k): str(v) for k, v in fixture.get("metar", {}).items()}

    def fetch_metar(self, airport: str = "OERK") -> dict[str, Any]:
        metar_by_airport = self._load_metar_records()
        raw = metar_by_airport.get(airport)
        if not raw:
            raise ValueError(f"No METAR available for {airport}")
        parsed = self.normalizer.parse_metar(raw)
        parsed["airport_name"] = SAUDI_AIRPORTS.get(airport, "Unknown")
        return parsed

    def fetch_all_airport_metar(self) -> dict[str, Any]:
        metar_by_airport = self._load_metar_records()
        airports: dict[str, Any] = {}
        dust_conditions: list[str] = []
        for icao in self.config.saudi_airports:
            raw = metar_by_airport.get(icao)
            if not raw:
                continue
            parsed = self.normalizer.parse_metar(raw)
            airports[icao] = parsed
            dust = self.normalizer.detect_dust_from_metar(parsed.get("weather_phenomena", []))
            if dust.get("dust_present"):
                dust_conditions.append(icao)
        return {"airports": airports, "dust_conditions": dust_conditions}

    def ingest_from_directory(self) -> dict[str, Any]:
        files_processed = 0
        alerts_count = 0
        metar_reports = 0
        if not self.incoming_dir.exists():
            return {"files_processed": 0, "alerts": 0, "metar_reports": 0}
        for path in self.incoming_dir.iterdir():
            if not path.is_file():
                continue
            files_processed += 1
            if path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                alerts_count += len(payload.get("alerts", []))
                if isinstance(payload.get("metar"), dict):
                    metar_reports += len(payload["metar"])
            elif path.suffix.lower() == ".csv":
                with path.open("r", encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                metar_reports += len(rows)
            elif path.suffix.lower() == ".txt":
                text = path.read_text(encoding="utf-8")
                metar_reports += len([line for line in text.splitlines() if line.strip().startswith("OE")])
        return {"files_processed": files_processed, "alerts": alerts_count, "metar_reports": metar_reports}

    def fetch(self, params: dict[str, Any]) -> Any:
        action = params.get("action", "alerts")
        if action == "metar":
            return self.fetch_metar(params.get("airport", "OERK"))
        if action == "all_metar":
            return self.fetch_all_airport_metar()
        if action == "ingest":
            return self.ingest_from_directory()
        return self.fetch_alerts()

    def normalize(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict) and "raw_metar" in raw_data:
            return self.normalizer.normalize_metar(raw_data)
        if isinstance(raw_data, dict) and "alerts" in raw_data:
            return {"alerts": [self.normalizer.normalize_alert(item) for item in raw_data.get("alerts", [])]}
        if isinstance(raw_data, dict) and "airports" in raw_data:
            observations = [self.normalizer.normalize_metar(item) for item in raw_data.get("airports", {}).values()]
            return {"observations": observations, "count": len(observations)}
        return raw_data

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            alerts = self.fetch_alerts()
            status = "ok"
            detail = f"source={alerts['source']} alerts={alerts['count']}"
        except Exception as exc:  # pragma: no cover
            status = "degraded"
            detail = str(exc)
        return {"status": status, "latency": round((time.perf_counter() - start) * 1000.0, 2), "detail": detail}
