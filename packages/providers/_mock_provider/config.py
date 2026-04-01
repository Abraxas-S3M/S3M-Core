"""Configuration model for the mock satellite provider adapter."""

from dataclasses import dataclass


@dataclass
class MockProviderConfig:
    """Static config used by mock provider for repeatable tactical tests."""

    fixture_path: str
    provider_id: str = "mock-satellite"
    provider_name: str = "Mock Satellite Provider"
