"""S3M GUI Bridge package for tactical operator workspaces.

Translates S3M-GUI frontend API expectations into internal S3M-Core
service calls so both systems can interoperate without endpoint rewrites.
"""

from src.api.gui_bridge.router import gui_bridge_router

__all__ = ["gui_bridge_router"]
