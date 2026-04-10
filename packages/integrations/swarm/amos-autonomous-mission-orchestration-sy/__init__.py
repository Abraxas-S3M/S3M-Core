"""amos-autonomous_mission_orchestration_system integration package."""

try:
    from .adapter import AmosAutonomousMissionOrchestrationAdapter
except ImportError:
    import importlib

    AmosAutonomousMissionOrchestrationAdapter = importlib.import_module(
        "packages.integrations.swarm.amos-autonomous-mission-orchestration-sy.adapter"
    ).AmosAutonomousMissionOrchestrationAdapter

__all__ = ["AmosAutonomousMissionOrchestrationAdapter"]
