from integration_sdk.base.provider_adapter import (
    OperatingMode,
    ProviderAdapter,
    ProviderCategory,
    ProviderHealth,
    ProviderManifest,
    ProviderTier,
)
from integration_sdk.registry.provider_registry import ProviderRegistry


class RegistryDummyAdapter(ProviderAdapter):
    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="registry-dummy",
            name="Registry Dummy",
            category=ProviderCategory.GEOINT,
            tier=ProviderTier.FREE,
            base_url="https://example.invalid",
            auth_type="none",
            rate_limit_rpm=5,
            supported_schemas=["NormalizedGeoObservation"],
            required_env_vars=[],
            description="registry dummy",
            docs_url="https://example.invalid/docs",
        )

    def validate_credentials(self) -> bool:
        return True

    def fetch(self, params=None):
        return {"items": [1]}

    def normalize(self, raw_data):
        return raw_data["items"]

    def health_check(self):
        return {
            "status": ProviderHealth.OK,
            "latency_ms": 1.0,
            "last_successful_fetch": None,
            "error_count": 0,
            "detail": "ok",
        }


def test_provider_registry_register_get_and_stats():
    registry = ProviderRegistry(config_path="/workspace/configs/integrations/providers.yaml")
    registry.register(RegistryDummyAdapter)

    adapter = registry.get("registry-dummy")
    assert adapter is not None
    assert adapter.get_manifest().provider_id == "registry-dummy"

    stats = registry.get_stats()
    assert stats["total_providers"] == 1
    assert stats["by_category"]["geoint"] == 1


def test_provider_registry_mode_switch_and_health():
    registry = ProviderRegistry(config_path="/workspace/configs/integrations/providers.yaml")
    registry.register(RegistryDummyAdapter)
    registry.set_mode("registry-dummy", OperatingMode.AIRGAPPED)
    adapter = registry.get("registry-dummy")
    assert adapter is not None
    assert adapter.get_mode() == OperatingMode.AIRGAPPED

    health = registry.health_check_all()
    assert health["registry-dummy"]["status"] == ProviderHealth.OK
