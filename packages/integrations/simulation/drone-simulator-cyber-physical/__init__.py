"""drone_simulator (cyber-physical) simulation integration package."""

try:
    from .adapter import DroneSimulatorcyberPhysicalAdapter
except ImportError:  # pragma: no cover - supports direct file collection contexts
    DroneSimulatorcyberPhysicalAdapter = None  # type: ignore[assignment]

__all__ = ["DroneSimulatorcyberPhysicalAdapter"]
