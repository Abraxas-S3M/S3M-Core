"""nav2 (ROS2 Navigation) integration package."""

try:
    from .adapter import Nav2ros2NavigationAdapter
except ImportError:
    import importlib

    Nav2ros2NavigationAdapter = importlib.import_module(
        "packages.integrations.navigation.nav2-ros2-navigation.adapter"
    ).Nav2ros2NavigationAdapter

__all__ = ["Nav2ros2NavigationAdapter"]
