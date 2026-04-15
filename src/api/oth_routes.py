"""API routes for OTH-Gold maritime track exchange.

Military/tactical context:
These endpoints expose coalition maritime track sharing so command centers can
maintain a synchronized over-the-horizon surface picture during naval ops.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.interop.oth import OTHGoldAdapter

oth_router = APIRouter()
_oth_adapter = OTHGoldAdapter()


class OTHConnectRequest(BaseModel):
    gateway_url: str = Field(..., min_length=3, max_length=2048)


class OTHPublishRequest(BaseModel):
    tracks: List[Dict[str, Any]] = Field(default_factory=list)


@oth_router.post("/interop/oth/connect")
async def connect_oth(req: OTHConnectRequest) -> Dict[str, Any]:
    ok = _oth_adapter.connect(req.gateway_url)
    if not ok:
        raise HTTPException(status_code=400, detail="failed to connect OTH-Gold gateway")
    return {"connected": ok, "gateway_url": req.gateway_url, "status": _oth_adapter.status()}


@oth_router.post("/interop/oth/publish")
async def publish_oth(req: OTHPublishRequest) -> Dict[str, Any]:
    if not _oth_adapter.connected:
        raise HTTPException(status_code=409, detail="OTH-Gold adapter is not connected")
    published = _oth_adapter.publish(req.tracks)
    return {"published": published, "status": _oth_adapter.status()}


@oth_router.get("/interop/oth/tracks")
async def receive_oth_tracks() -> Dict[str, Any]:
    tracks = _oth_adapter.receive()
    return {"tracks": tracks, "total": len(tracks)}


@oth_router.get("/interop/oth/status")
async def oth_status() -> Dict[str, Any]:
    return _oth_adapter.status()
