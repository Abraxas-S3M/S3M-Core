"""REST routes for JREAP-C Link 16 gateway control and monitoring."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Query
import yaml

from services.interop.jreap import JREAPBridge

jreap_router = APIRouter()

_DEFAULT_JREAP_CONFIG = {
    "enabled": False,
    "listen_port": 5555,
    "supported_j_series": ["J2.2", "J3.2", "J3.5", "J13.2"],
    "crossfeed_to_cot": True,
    "crossfeed_to_dis": True,
}


def _load_jreap_config() -> dict:
    config_path = Path(__file__).resolve().parents[2] / "configs" / "interop-extended.yaml"
    merged = dict(_DEFAULT_JREAP_CONFIG)
    if not config_path.exists():
        return {"jreap": merged}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"jreap": merged}
    file_cfg = data.get("jreap", {})
    if isinstance(file_cfg, dict):
        merged.update(file_cfg)
    return {"jreap": merged}


_jreap_bridge = JREAPBridge(_load_jreap_config())


@jreap_router.post("/interop/jreap/start")
async def start_jreap_listener(port: int | None = Query(default=None, ge=1, le=65535)) -> Dict[str, Any]:
    target_port = int(port or _jreap_bridge.listen_port)
    started = _jreap_bridge.start_listener(target_port)
    return {
        "started": started,
        "listen_port": target_port,
        "status": "operational" if started else "failed",
    }


@jreap_router.post("/interop/jreap/stop")
async def stop_jreap_listener() -> Dict[str, Any]:
    _jreap_bridge.stop_listener()
    return {"stopped": True, "status": "stopped"}


@jreap_router.get("/interop/jreap/tracks")
async def get_jreap_tracks() -> Dict[str, Any]:
    _jreap_bridge.process_received()
    tracks = _jreap_bridge.get_tracks()
    return {"tracks": tracks, "total": len(tracks)}


@jreap_router.get("/interop/jreap/stats")
async def get_jreap_stats() -> Dict[str, Any]:
    return _jreap_bridge.get_stats()


@jreap_router.get("/interop/jreap/status")
async def get_jreap_status() -> Dict[str, Any]:
    return _jreap_bridge.health_check()
