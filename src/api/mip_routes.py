"""FastAPI routes for MIP gateway interoperability services."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import yaml

from services.interop.mip import MIPGateway


class MIPConnectRequest(BaseModel):
    partner_url: str = Field(..., min_length=1)


class MIPPublishRequest(BaseModel):
    oig_category: str
    items: List[Any] = Field(default_factory=list)
    owning_unit: str = "s3m-hq"


class MIPCopRequest(BaseModel):
    tracks: List[Dict[str, Any]] = Field(default_factory=list)


def _load_mip_config() -> dict:
    defaults = {
        "baseline": "4.3",
        "data_model": "MIM",
        "gateway_url": None,
        "oig_categories": ["operations", "intelligence", "logistics", "plans", "cop"],
        "publish_interval_seconds": 10,
        "outbox_dir": "data/interop/mip_outbox/",
    }
    path = Path("configs/interop-extended.yaml")
    if not path.exists():
        return defaults
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    mip_cfg = payload.get("mip", {})
    if isinstance(mip_cfg, dict):
        defaults.update(mip_cfg)
    return defaults


mip_router = APIRouter()
_mip_gateway = MIPGateway(config=_load_mip_config())


@mip_router.post("/interop/mip/connect")
async def connect_mip(req: MIPConnectRequest) -> Dict[str, Any]:
    connected = _mip_gateway.connect(req.partner_url)
    if not connected:
        raise HTTPException(status_code=400, detail=_mip_gateway.last_error or "Connection failed")
    return {"connected": connected, "status": _mip_gateway.health_check()}


@mip_router.post("/interop/mip/publish")
async def publish_mip(req: MIPPublishRequest) -> Dict[str, Any]:
    oig = _mip_gateway.data_model.create_oig(req.oig_category, req.owning_unit)
    for item in req.items:
        if isinstance(item, dict):
            if "mission_type" in item or "action_type" in item:
                task = _mip_gateway.mapper.s3m_mission_to_mip_task(item)
                oig.items.append(task.action_id)
            else:
                obj, loc = _mip_gateway.mapper.s3m_track_to_mip(item)
                oig.items.extend([obj.object_item_id, loc.object_item_id])
        else:
            oig.items.append(str(item))
    ok = _mip_gateway.publish_oig(oig)
    return {
        "published": ok,
        "oig_id": oig.oig_id,
        "oig_category": oig.category,
        "item_count": len(oig.items),
        "status": _mip_gateway.health_check(),
    }


@mip_router.post("/interop/mip/cop")
async def publish_cop(req: Optional[MIPCopRequest] = None) -> Dict[str, Any]:
    tracks = req.tracks if req else []
    published = _mip_gateway.exchange_cop(tracks)
    return {"published_tracks": published, "status": _mip_gateway.health_check()}


@mip_router.get("/interop/mip/oigs")
async def list_mip_oigs() -> Dict[str, Any]:
    return {
        "available_oigs": list(_mip_gateway.available_oigs),
        "partner_oigs": list(_mip_gateway.partner_oigs),
        "published_oigs": [oig.oig_id for oig in _mip_gateway.published_oigs],
    }


@mip_router.get("/interop/mip/received")
async def received_mip_items() -> Dict[str, Any]:
    updates = _mip_gateway.receive_updates()
    return {"count": len(updates), "items": updates}


@mip_router.get("/interop/mip/status")
async def mip_status() -> Dict[str, Any]:
    return _mip_gateway.health_check()
