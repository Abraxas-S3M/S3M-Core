"""gz-sim (Gazebo Sim) simulation integration package."""

try:
    from .adapter import GzSimgazeboSimAdapter
except ImportError:  # pragma: no cover - supports direct file collection contexts
    GzSimgazeboSimAdapter = None  # type: ignore[assignment]

__all__ = ["GzSimgazeboSimAdapter"]
