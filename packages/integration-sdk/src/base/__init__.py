"""Base contracts for provider integrations."""

from .provider_adapter import (
    OperatingMode,
    ProviderAdapter,
    ProviderCategory,
    ProviderHealth,
    ProviderManifest,
    ProviderTier,
)
from .auth_strategy import AuthStrategy
from .normalizer import BaseNormalizer
from .fetch_job import FetchJobConfig, FetchJobRunner

__all__ = [
    "AuthStrategy",
    "BaseNormalizer",
    "FetchJobConfig",
    "FetchJobRunner",
    "OperatingMode",
    "ProviderAdapter",
    "ProviderCategory",
    "ProviderHealth",
    "ProviderManifest",
    "ProviderTier",
]
