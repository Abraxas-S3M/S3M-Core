"""Elm adapter for sovereign identity and records services."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier

from .config import ElmConfig
from .normalizer import ElmNormalizer


class ElmAdapter(ProviderAdapter):
    def __init__(self, config: ElmConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or ElmConfig()
        self.normalizer = ElmNormalizer()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _has_credentials(self) -> bool:
        client_id = os.getenv("S3M_ELM_CLIENT_ID") or os.getenv("ELM_CLIENT_ID")
        client_secret = os.getenv("S3M_ELM_CLIENT_SECRET") or os.getenv("ELM_CLIENT_SECRET")
        return bool(client_id and client_secret)

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="sovereign-elm",
            name="Elm Sovereign Government Services",
            category=ProviderCategory.SOVEREIGN_REGIONAL,
            tier=ProviderTier.GOVERNMENT,
            base_url=self.config.api_url,
            auth_type="oauth2",
            rate_limit_rpm=self.config.rate_limit_rpm,
            supported_schemas=["IdentityVerification", "VehicleRegistration"],
            required_env_vars=["ELM_CLIENT_ID", "ELM_CLIENT_SECRET"],
            optional_env_vars=[],
            description="Elm identity and government records integration with strict PII controls.",
            docs_url="https://elm.sa",
            airgap_capable=True,
            enabled=True,
            tags=["elm", "identity", "saudi", "sovereign", "confidential"],
        )

    def validate_credentials(self) -> bool:
        if self.mode == "airgapped":
            return (self._fixture_dir() / "fixtures" / "identity_verified.json").exists()
        return self._has_credentials()

    def sanitize_for_logging(self, data: dict[str, Any]) -> dict[str, Any]:
        # Tactical context: personnel identity payloads are confidential and must never leak to logs.
        safe = {
            "verified": bool(data.get("verified", False)),
            "status": data.get("status", "unknown"),
        }
        if "record_type" in data:
            safe["record_type"] = data["record_type"]
        if "registered" in data:
            safe["registered"] = bool(data.get("registered", False))
        if "owner_type" in data:
            safe["owner_type"] = data.get("owner_type")
        if "vehicle_type" in data:
            safe["vehicle_type"] = data.get("vehicle_type")
        return safe

    def verify_identity(self, national_id: str) -> dict[str, Any]:
        clean_id = str(national_id).strip()
        if not clean_id.isdigit() or len(clean_id) < 6:
            return {"verified": False, "status": "invalid_input", "classification": self.config.data_classification}

        if self.mode == "airgapped":
            payload = self._load_fixture_json("identity_verified.json")
            if clean_id.endswith("0000"):
                payload = self._load_fixture_json("identity_not_found.json")
            payload["classification"] = self.config.data_classification
            return payload

        return {"verified": False, "status": "api_not_configured", "classification": self.config.data_classification}

    def lookup_vehicle(self, plate_number: str) -> dict[str, Any]:
        plate = str(plate_number).strip().upper()
        if not plate:
            return {"registered": False, "status": "invalid_input", "classification": self.config.data_classification}

        if self.mode == "airgapped":
            payload = self._load_fixture_json("vehicle_military.json")
            payload["classification"] = self.config.data_classification
            return payload

        return {
            "registered": False,
            "owner_type": "unknown",
            "vehicle_type": "unknown",
            "classification": self.config.data_classification,
        }

    def search_records(self, record_type: str, query: str) -> dict[str, Any]:
        return {
            "record_type": record_type,
            "status": "available" if query else "invalid_query",
            "results": [],
            "classification": self.config.data_classification,
        }

    def fetch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        endpoint = params.get("endpoint", "identity")
        if endpoint == "identity":
            return self.verify_identity(str(params.get("national_id", "000000")))
        if endpoint == "vehicle":
            return self.lookup_vehicle(str(params.get("plate_number", "")))
        if endpoint == "records":
            return self.search_records(str(params.get("record_type", "general")), str(params.get("query", "")))
        return self.verify_identity(str(params.get("national_id", "000000")))

    def normalize(self, raw_data: dict[str, Any]) -> list[dict[str, Any]]:
        if "registered" in raw_data:
            return [self.normalizer.normalize_vehicle_result(raw_data)]
        return [self.normalizer.normalize_identity_result(raw_data)]

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok" if self.validate_credentials() else "degraded",
            "detail": {
                "mode": self.mode,
                "classification": self.config.data_classification,
                "services": self.config.service_types,
            },
        }
