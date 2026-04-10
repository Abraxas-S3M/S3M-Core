"""rpg_quadrotor_control (related) integration package."""

try:
    from .adapter import RpgQuadrotorControlrelatedAdapter
except ImportError:
    import importlib

    RpgQuadrotorControlrelatedAdapter = importlib.import_module(
        "packages.integrations.navigation.rpg-quadrotor-control-related.adapter"
    ).RpgQuadrotorControlrelatedAdapter

__all__ = ["RpgQuadrotorControlrelatedAdapter"]
