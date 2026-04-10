"""awesome-tinyml integration package."""

try:
    from .adapter import AwesomeTinymlAdapter
except ImportError:
    import importlib

    AwesomeTinymlAdapter = importlib.import_module(
        "packages.integrations.navigation.awesome-tinyml.adapter"
    ).AwesomeTinymlAdapter

__all__ = ["AwesomeTinymlAdapter"]
