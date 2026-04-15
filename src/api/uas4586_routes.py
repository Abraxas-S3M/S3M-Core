"""FastAPI routes for STANAG 4586 UAS interoperability."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import yaml

from services.interop.uas4586 import UAS4586Interface, UAS4586MessageHandler

uas4586_router = APIRouter()


class UASRegisterRequest(BaseModel):
    uav_id: str = Field(..., min_length=1, max_length=128)
    uav_type: str = Field(..., min_length=1, max_length=128)
    capabilities: List[str] = Field(default_factory=list)


class VehicleStatusRequest(BaseModel):
    uav_id: str = Field(..., min_length=1, max_length=128)
    status: Dict[str, Any] = Field(default_factory=dict)


class PayloadStatusRequest(BaseModel):
    uav_id: str = Field(..., min_length=1, max_length=128)
    payload: Dict[str, Any] = Field(default_factory=dict)


class ISRProductRequest(BaseModel):
    uav_id: str = Field(..., min_length=1, max_length=128)
    product: Dict[str, Any] = Field(default_factory=dict)


def _load_uas4586_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "max_loi": 3,
        "registered_uavs": [],
        "publish_interval_seconds": 1,
    }
    config_path = Path(__file__).resolve().parents[2] / "configs" / "interop-extended.yaml"
    if not config_path.exists():
        return defaults
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    cfg = payload.get("uas4586", {})
    if isinstance(cfg, dict):
        defaults.update(cfg)
    return defaults


_uas4586 = UAS4586Interface(config=_load_uas4586_config(), message_handler=UAS4586MessageHandler())


@uas4586_router.post("/interop/uas4586/register")
async def register_uav(req: UASRegisterRequest) -> Dict[str, Any]:
    try:
        registration = _uas4586.register_uav(req.uav_id, req.uav_type, req.capabilities)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"registered": True, "uav": registration}


@uas4586_router.post("/interop/uas4586/status/vehicle")
async def publish_vehicle_status(req: VehicleStatusRequest) -> Dict[str, Any]:
    ok = _uas4586.publish_vehicle_status(req.uav_id, req.status)
    if not ok:
        detail = _uas4586.health_check().get("last_error") or "vehicle status publish failed"
        raise HTTPException(status_code=400, detail=detail)
    return {"published": True}


@uas4586_router.post("/interop/uas4586/status/payload")
async def publish_payload_status(req: PayloadStatusRequest) -> Dict[str, Any]:
    ok = _uas4586.publish_payload_status(req.uav_id, req.payload)
    if not ok:
        detail = _uas4586.health_check().get("last_error") or "payload status publish failed"
        raise HTTPException(status_code=400, detail=detail)
    return {"published": True}


@uas4586_router.post("/interop/uas4586/isr")
async def publish_isr_product(req: ISRProductRequest) -> Dict[str, Any]:
    ok = _uas4586.publish_isr_product(req.uav_id, req.product)
    if not ok:
        detail = _uas4586.health_check().get("last_error") or "isr product publish failed"
        raise HTTPException(status_code=400, detail=detail)
    return {"published": True}


@uas4586_router.get("/interop/uas4586/uavs")
async def list_registered_uavs() -> List[Dict[str, Any]]:
    return _uas4586.get_registered_uavs()


@uas4586_router.get("/interop/uas4586/status")
async def uas4586_status() -> Dict[str, Any]:
    return _uas4586.health_check()
