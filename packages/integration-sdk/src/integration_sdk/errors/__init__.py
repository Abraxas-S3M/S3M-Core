"""Structured integration error hierarchy."""

from .integration_errors import (
    AirgapViolationError,
    AuthenticationError,
    CircuitBreakerOpenError,
    IntegrationConfigurationError,
    IntegrationError,
    ProviderFetchError,
    ProviderNotFoundError,
    RateLimitExceededError,
)

__all__ = [
    "AirgapViolationError",
    "AuthenticationError",
    "CircuitBreakerOpenError",
    "IntegrationConfigurationError",
    "IntegrationError",
    "ProviderFetchError",
    "ProviderNotFoundError",
    "RateLimitExceededError",
]
