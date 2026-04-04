"""Main GUI Bridge router — assembled here, mounted once in server.py."""

from fastapi import APIRouter

from src.api.gui_bridge.auth_routes import auth_router
from src.api.gui_bridge.ai_routes import ai_router
from src.api.gui_bridge.workspace_routes import workspace_router

gui_bridge_router = APIRouter()

gui_bridge_router.include_router(auth_router)
gui_bridge_router.include_router(ai_router)
gui_bridge_router.include_router(workspace_router)
