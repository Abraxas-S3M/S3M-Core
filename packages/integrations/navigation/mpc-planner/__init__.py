"""mpc_planner navigation integration package."""

try:
    from .adapter import MpcPlannerAdapter
except ImportError:
    import importlib

    MpcPlannerAdapter = importlib.import_module(
        "packages.integrations.navigation.mpc-planner.adapter"
    ).MpcPlannerAdapter

__all__ = ["MpcPlannerAdapter"]
