"""Ardupilot_Multiagent_Simulation integration package."""

try:
    from .adapter import ArdupilotMultiagentSimulationAdapter
except ImportError:
    import importlib

    ArdupilotMultiagentSimulationAdapter = importlib.import_module(
        "packages.integrations.swarm.ardupilot-multiagent-simulation.adapter"
    ).ArdupilotMultiagentSimulationAdapter

__all__ = ["ArdupilotMultiagentSimulationAdapter"]
