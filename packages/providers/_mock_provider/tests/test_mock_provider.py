from integration_sdk.base.provider_adapter import OperatingMode

from packages.providers._mock_provider.adapter import MockSatelliteProvider
from packages.schemas.geospatial.models import NormalizedGeoObservation


def test_mock_provider_validate_fetch_normalize(monkeypatch):
    monkeypatch.setenv("S3M_MOCK_API_KEY", "any_value_works_for_mock")
    adapter = MockSatelliteProvider(mode=OperatingMode.ONLINE)

    assert adapter.validate_credentials() is True
    raw = adapter.fetch()
    assert "observations" in raw

    normalized = adapter.normalize(raw)
    assert len(normalized) == 1
    assert isinstance(normalized[0], NormalizedGeoObservation)


def test_mock_provider_airgapped_mode(monkeypatch):
    monkeypatch.setenv("S3M_MOCK_API_KEY", "any_value_works_for_mock")
    adapter = MockSatelliteProvider(mode=OperatingMode.AIRGAPPED)
    raw = adapter.fetch()
    normalized = adapter.normalize(raw)
    assert len(normalized) == 1
