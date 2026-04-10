"""Autonomous_UAVs_Swarm_Mission integration package."""

try:
    from .adapter import AutonomousUavsSwarmMissionAdapter
except ImportError:
    import importlib

    AutonomousUavsSwarmMissionAdapter = importlib.import_module(
        "packages.integrations.swarm.autonomous-uavs-swarm-mission.adapter"
    ).AutonomousUavsSwarmMissionAdapter

__all__ = ["AutonomousUavsSwarmMissionAdapter"]
