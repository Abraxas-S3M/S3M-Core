"""
S3M Edge Node Standalone Server
UNCLASSIFIED - FOUO

Lightweight FastAPI server for containerised edge node deployment.
Runs independently of the main S3M API and serves edge orchestration only.
"""

from __future__ import annotations

import json
import logging
import os
import signal
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.edge_compute.api import edge_compute_router, set_manager
from src.edge_compute.manager import EdgeComputeManager

logging.basicConfig(level=os.environ.get("S3M_LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("s3m.edge.server")

app = FastAPI(
    title="S3M Edge Node",
    description="Sovereign Saudi Strategic Model - Edge CPU Node",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(edge_compute_router, prefix="/edge", tags=["Edge Compute"])

_manager: EdgeComputeManager | None = None


def _load_config() -> Dict[str, Any]:
    """Load runtime parameters from a local shared config file."""
    config_path = os.environ.get("S3M_CONFIG_PATH", "/opt/s3m/config/params.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    return {}


def _init_manager() -> EdgeComputeManager:
    """Initialize or reinitialize the edge compute manager."""
    config = _load_config()
    manager = EdgeComputeManager(
        container_runtime=str(config.get("container_runtime", "docker")),
        scheduling_policy=str(config.get("scheduling_policy", "adaptive")),
    )
    set_manager(manager)
    return manager


@app.on_event("startup")
async def startup() -> None:
    global _manager
    _manager = _init_manager()
    node_id = os.environ.get("S3M_NODE_ID", "auto")
    logger.info("S3M Edge Node started: node_id=%s", node_id)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _manager is not None:
        _manager.shutdown()
    logger.info("S3M Edge Node shutdown")


def _handle_sighup(signum: int, frame: Any) -> None:
    # Tactical deployments can rotate mission config without full process restart.
    _ = signum
    _ = frame
    logger.info("SIGHUP received - reloading edge node config")
    global _manager
    _manager = _init_manager()


signal.signal(signal.SIGHUP, _handle_sighup)


@app.get("/")
async def root() -> Dict[str, str]:
    return {
        "service": "S3M Edge Node",
        "node_id": os.environ.get("S3M_NODE_ID", "auto"),
        "status": "online",
    }
