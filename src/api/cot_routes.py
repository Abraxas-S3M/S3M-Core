"""CoT interoperability API endpoints for ATAK/TAK gateway control."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.interop.cot import CotBridge, CotEventFactory, CotTransport

cot_router = APIRouter()


class CotConnectRequest(BaseModel):
    transport: Literal["multicast", "tak_server"]
    config: Dict[str, Any] = Field(default_factory=dict)


class CotPublishRequest(BaseModel):
    tracks: List[Dict[str, Any]] = Field(default_factory=list)


_transport = CotTransport({})
_event_factory = CotEventFactory({})
_bridge = CotBridge(_transport, _event_factory)


def _reconfigure(config: dict) -> None:
    global _transport, _event_factory, _bridge
    cfg = dict(config or {})
    _transport = CotTransport(cfg)
    _event_factory = CotEventFactory(cfg)
    _bridge = CotBridge(_transport, _event_factory)


@cot_router.post("/interop/cot/connect")
async def cot_connect(req: CotConnectRequest) -> Dict[str, Any]:
    _reconfigure(req.config)
    if req.transport == "multicast":
        ok = _transport.connect_multicast()
    else:
        url = str(req.config.get("tak_server_url") or req.config.get("url") or "").strip()
        ok = _transport.connect_tak_server(url)
    if not ok:
        raise HTTPException(status_code=503, detail="Unable to establish CoT transport")
    return {"connected": True, "transport": req.transport, "status": _transport.health_check()}


@cot_router.post("/interop/cot/disconnect")
async def cot_disconnect() -> Dict[str, Any]:
    _transport.disconnect()
    return {"connected": False}


@cot_router.post("/interop/cot/publish")
async def cot_publish(req: CotPublishRequest) -> Dict[str, Any]:
    published = _bridge.publish_tracks(req.tracks)
    return {"published": published, "requested": len(req.tracks)}


@cot_router.get("/interop/cot/tracks")
async def cot_tracks() -> List[Dict[str, Any]]:
    return _bridge.ingest_received()


@cot_router.get("/interop/cot/stats")
async def cot_stats() -> Dict[str, Any]:
    return _bridge.get_stats()


@cot_router.get("/interop/cot/status")
async def cot_status() -> Dict[str, Any]:
    return {"transport": _transport.health_check(), "bridge": _bridge.get_stats()}

