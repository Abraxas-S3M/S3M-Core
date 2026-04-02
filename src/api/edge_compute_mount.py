"""
S3M API Server - Edge Compute Router Mount
UNCLASSIFIED - FOUO

Helper for integrating edge compute routes into the main API server.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("s3m.api.edge_mount")


def mount_edge_compute(app: "FastAPI") -> None:
    """
    Mount edge compute endpoints on the main S3M API server.

    This registers /edge/* APIs and /dashboard/edge* read-only views.
    """
    try:
        from src.edge_compute.api import edge_compute_router, set_manager
        from src.edge_compute.manager import EdgeComputeManager

        manager = EdgeComputeManager()
        set_manager(manager)

        app.include_router(
            edge_compute_router,
            prefix="/edge",
            tags=["Edge Compute"],
        )

        _mount_dashboard_endpoint(app, manager)

        @app.on_event("shutdown")
        async def _shutdown_edge() -> None:
            manager.shutdown()

        logger.info("Edge compute endpoints mounted at /edge/*")

    except ImportError as exc:
        logger.warning("Edge compute module not available: %s", exc)


def _mount_dashboard_endpoint(app: "FastAPI", manager) -> None:
    """Add dashboard-style aggregated edge compute endpoints."""
    try:
        from src.dashboard.providers.edge_compute_provider import EdgeComputeDashProvider

        provider = EdgeComputeDashProvider()
        provider.set_manager(manager)

        @app.get("/dashboard/edge", tags=["Dashboard"])
        async def dashboard_edge_overview():
            return provider.get_full_overview()

        @app.get("/dashboard/edge/network", tags=["Dashboard"])
        async def dashboard_edge_network():
            return provider.get_edge_network_overview()

        @app.get("/dashboard/edge/training", tags=["Dashboard"])
        async def dashboard_edge_training():
            return provider.get_self_training_status()

        @app.get("/dashboard/edge/replicas", tags=["Dashboard"])
        async def dashboard_edge_replicas():
            return provider.get_replica_fleet()

        @app.get("/dashboard/edge/data", tags=["Dashboard"])
        async def dashboard_edge_data():
            return provider.get_data_generation_status()

        @app.get("/dashboard/edge/sandboxes", tags=["Dashboard"])
        async def dashboard_edge_sandboxes():
            return provider.get_sandbox_fleet()

        @app.get("/dashboard/edge/compute", tags=["Dashboard"])
        async def dashboard_edge_compute():
            return provider.get_hetero_compute_status()

        logger.info("Edge compute dashboard endpoints mounted at /dashboard/edge/*")

    except ImportError:
        logger.debug("Dashboard edge provider not available")
