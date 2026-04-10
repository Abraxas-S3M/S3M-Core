"""bcr_arm simulation integration package."""

try:
    from .adapter import BcrArmAdapter
except ImportError:  # pragma: no cover - supports direct file collection contexts
    BcrArmAdapter = None  # type: ignore[assignment]

__all__ = ["BcrArmAdapter"]
