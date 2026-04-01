"""Mock provider adapter implementing the standard provider lifecycle."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from integration_sdk.auth.secret_provider import SecretProvider
from integration_sdk.base.provider_adapter import (
    OperatingMode,
    ProviderAdapter,
    ProviderCategory,
    ProviderHealth,
    ProviderManifest,
    ProviderTier,
)

from .config import MockProviderConfig
from .normalizer import MockNormalizer


class MockSatelliteProvider(ProviderAdapter):
    """Reference GEOINT adapter used to validate framework behavior safely."""

    def __init__(self, mode: OperatingMode = OperatingMode.ONLINE):
        super().__init__(mode=mode)
        fixture = Path(__file__).resolve().parent / "fixtures" / "mock_satellite_response.json"
        self.config = MockProviderConfig(fixture_path=str(fixture))
        self.secret_provider = SecretProvider(prefix="S3M")
        self.normalizer = MockNormalizer(
            provider_id=self.config.provider_id,
            provider_name=self.config.provider_name,
        )

    def get_manifest(self) -> ProviderManifest:
        if self._manifest is None:
            self._manifest = ProviderManifest(
                provider_id=self.config.provider_id,
                name=self.config.provider_name,
                category=ProviderCategory.GEOINT,
                tier=ProviderTier.FREE,
                base_url="https://mock.provider.local",
                auth_type="api_key",
                rate_limit_rpm=60,
                supported_schemas=["NormalizedGeoObservation"],
                required_env_vars=["S3M_MOCK_API_KEY"],
                description="Mock GEOINT provider for integration framework testing.",
                docs_url="https://example.invalid/mock-provider-docs",
                airgap_capable=True,
                enabled=True,
                tags=["mock", "reference", "geoint"],
            )
        return self._manifest

    def validate_credentials(self) -> bool:
        # Tactical note: field kits must verify credential wiring before mission ingest.
        return self.secret_provider.has("MOCK_API_KEY")

    def _load_fixture(self) -> Dict[str, Any]:
        with open(self.config.fixture_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def fetch(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        # Tactical note: both online and air-gapped modes consume approved local cache fixtures.
        payload = self._load_fixture()
        self._last_fetch_at = datetime.now(timezone.utc)
        self._fetch_count += 1
        self._last_health = ProviderHealth.OK
        return payload

    def normalize(self, raw_data: Dict[str, Any]) -> List[Any]:
        return self.normalizer.normalize(raw_data)

    def health_check(self) -> Dict[str, Any]:
        if not Path(self.config.fixture_path).exists():
            self._last_health = ProviderHealth.FAILING
            self._error_count += 1
            return {
                "status": ProviderHealth.FAILING,
                "latency_ms": None,
                "last_successful_fetch": self._last_fetch_at,
                "error_count": self._error_count,
                "detail": "Fixture missing",
            }

        self._last_health = ProviderHealth.OK
        return {
            "status": ProviderHealth.OK,
            "latency_ms": 1.0,
            "last_successful_fetch": self._last_fetch_at,
            "error_count": self._error_count,
            "detail": "Mock provider healthy",
        }
