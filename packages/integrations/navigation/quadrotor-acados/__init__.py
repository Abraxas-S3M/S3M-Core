"""quadrotor_acados navigation integration package."""

try:
    from .adapter import QuadrotorAcadosAdapter
except ImportError:
    import importlib

    QuadrotorAcadosAdapter = importlib.import_module(
        "packages.integrations.navigation.quadrotor-acados.adapter"
    ).QuadrotorAcadosAdapter

__all__ = ["QuadrotorAcadosAdapter"]
