"""Military_Drones (VorteX) simulation integration package."""

try:
    from .adapter import MilitaryDronesvortexAdapter
except ImportError:  # pragma: no cover - supports direct file collection contexts
    MilitaryDronesvortexAdapter = None  # type: ignore[assignment]

__all__ = ["MilitaryDronesvortexAdapter"]
