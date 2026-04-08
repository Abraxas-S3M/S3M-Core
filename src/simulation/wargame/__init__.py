"""Exports for Layer 04 wargaming components."""

from src.simulation.wargame.force_builder import ForceBuilder
from src.simulation.wargame.scenario_engine import ScenarioEngine

try:  # pragma: no cover - optional LLM stack may be unavailable in slim environments
    from src.simulation.wargame.opfor_generator import OpForGenerator
except Exception:  # pragma: no cover - keep scenario engine importable without LLM registry
    OpForGenerator = None  # type: ignore[assignment]

try:  # pragma: no cover - optional LLM stack may be unavailable in slim environments
    from src.simulation.wargame.aar_generator import AARGenerator
except Exception:  # pragma: no cover
    AARGenerator = None  # type: ignore[assignment]

try:  # pragma: no cover - depends on optional OpFor/AAR imports
    from src.simulation.wargame.scenario_runner import ScenarioRunner
except Exception:  # pragma: no cover
    ScenarioRunner = None  # type: ignore[assignment]

__all__ = [
    "ScenarioEngine",
    "ScenarioRunner",
    "OpForGenerator",
    "AARGenerator",
    "ForceBuilder",
]
