"""
S3M GUI Bridge — translates S3M-GUI frontend API expectations
into internal S3M-Core service calls.

The GUI expects all endpoints under /api/v1/workspaces/{domain}/{resource}.
The existing backend uses /dashboard/*, /threats/*, /comms/*, etc.
This bridge layer provides route translation, response reshaping,
and data aggregation so the two can connect without modifying either.
"""

from src.api.gui_bridge.router import gui_bridge_router

__all__ = ["gui_bridge_router"]
