"""acados navigation integration package."""

try:
    from .adapter import AcadosAdapter
except ImportError:
    import importlib

    AcadosAdapter = importlib.import_module(
        "packages.integrations.navigation.acados.adapter"
    ).AcadosAdapter

__all__ = ["AcadosAdapter"]
