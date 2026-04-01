"""Structured exceptions for integration framework operations."""


class IntegrationError(Exception):
    """Base class for integration framework failures."""


class IntegrationConfigurationError(IntegrationError):
    """Raised when provider configuration is invalid."""


class ProviderNotFoundError(IntegrationError):
    """Raised when requesting an unregistered provider."""


class AuthenticationError(IntegrationError):
    """Raised for missing or invalid provider credentials."""


class ProviderFetchError(IntegrationError):
    """Raised when provider fetch attempts fail after retries."""


class RateLimitExceededError(IntegrationError):
    """Raised when a provider exceeds configured request budget."""


class CircuitBreakerOpenError(IntegrationError):
    """Raised when requests are blocked by an open circuit breaker."""


class AirgapViolationError(IntegrationError):
    """Raised when outbound access is attempted in air-gapped mode."""
