"""S3M GUI Bridge package for tactical operator workspaces.

Translates S3M-GUI frontend API expectations into internal S3M-Core
service calls so both systems can interoperate without endpoint rewrites.
"""

__all__ = ["gui_bridge_router"]


def __getattr__(name: str):
    if name == "gui_bridge_router":
        from src.api.gui_bridge.router import gui_bridge_router

        return gui_bridge_router
    raise AttributeError(name)
