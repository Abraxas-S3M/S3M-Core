from datetime import datetime, timezone

from integration_sdk.base.provider_adapter import (
    OperatingMode,
    ProviderAdapter,
    ProviderCategory,
    ProviderHealth,
    ProviderManifest,
    ProviderTier,
)


class DummyAdapter(ProviderAdapter):
    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="dummy",
            name="Dummy",
            category=ProviderCategory.GEOINT,
            tier=ProviderTier.FREE,
            base_url="https://example.invalid",
            auth_type="none",
            rate_limit_rpm=10,
            supported_schemas=["NormalizedGeoObservation"],
            required_env_vars=[],
            description="dummy",
            docs_url="https://example.invalid/docs",
        )

    def validate_credentials(self) -> bool:
        return True

    def fetch(self, params=None):
        self._last_fetch_at = datetime.now(timezone.utc)
        self._fetch_count += 1
        self._last_health = ProviderHealth.OK
        return {"items": [{"value": 1}]}

    def normalize(self, raw_data):
        return raw_data["items"]

    def health_check(self):
        return {
            "status": ProviderHealth.OK,
            "latency_ms": 1.0,
            "last_successful_fetch": self._last_fetch_at,
            "error_count": self._error_count,
            "detail": "ok",
        }


def test_provider_adapter_fetch_and_stats():
    adapter = DummyAdapter(mode=OperatingMode.ONLINE)
    records = adapter.fetch_and_normalize()
    assert records == [{"value": 1}]
    stats = adapter.get_stats()
    assert stats["provider_id"] == "dummy"
    assert stats["fetch_count"] == 1
    assert stats["mode"] == "online"


def test_provider_mode_switching():
    adapter = DummyAdapter(mode=OperatingMode.ONLINE)
    assert not adapter.is_airgapped()
    adapter.set_mode(OperatingMode.AIRGAPPED)
    assert adapter.is_airgapped()
