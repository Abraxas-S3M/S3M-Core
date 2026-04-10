"""SDV (Synthetic Data Vault) simulation integration package."""

try:
    from .adapter import SdvsyntheticDataVaultAdapter
except ImportError:  # pragma: no cover - supports direct file collection contexts
    SdvsyntheticDataVaultAdapter = None  # type: ignore[assignment]

__all__ = ["SdvsyntheticDataVaultAdapter"]
