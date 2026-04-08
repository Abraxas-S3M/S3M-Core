"""Main GUI Bridge router — assembled here, mounted once in server.py."""

from fastapi import APIRouter

# Import sub-routers (will be created in subsequent prompts)
from src.api.gui_bridge.ai_routes import ai_router
from src.api.gui_bridge.auth_routes import auth_router
from src.api.gui_bridge.system_routes import system_router
from src.api.gui_bridge.ws_bridge import ws_router

gui_bridge_router = APIRouter()

# Auth endpoints: /api/v1/auth/*
gui_bridge_router.include_router(auth_router)

# AI chat endpoint: /api/v1/ai/*
gui_bridge_router.include_router(ai_router)

# System status endpoint: /api/v1/system/*
gui_bridge_router.include_router(system_router)

# Note: workspace_routes will be included here once adapters are built.
# ws_router is mounted separately at root level in server.py because
# WebSocket routes cannot have path prefixes in FastAPI.
