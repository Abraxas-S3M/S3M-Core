from integration_sdk.registry.provider_registry import ProviderRegistry

from packages.providers._mock_provider.adapter import MockSatelliteProvider


def test_mock_provider_registry_flow(monkeypatch):
    monkeypatch.setenv("S3M_MOCK_API_KEY", "any_value_works_for_mock")

    registry = ProviderRegistry(config_path="/workspace/configs/integrations/providers.yaml")
    registry.register(MockSatelliteProvider)

    provider = registry.get("mock-satellite")
    assert provider is not None
    assert provider.validate_credentials() is True

    normalized = provider.fetch_and_normalize()
    assert len(normalized) == 1
    assert normalized[0].satellite == "mock-sat-1"

    health = registry.health_check_all()
    assert health["mock-satellite"]["status"].value == "ok"
