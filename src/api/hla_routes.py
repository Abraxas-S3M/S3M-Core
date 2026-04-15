"""FastAPI routes for HLA federation lifecycle and publication control."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import yaml

from services.interop.hla.federate_adapter import HLAFederateAdapter


class FederationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    fom_path: str = Field(..., min_length=1, max_length=2048)


class FederationJoinRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class HLAPublishRequest(BaseModel):
    class_name: str = Field(..., min_length=1, max_length=128)
    attributes: List[str] = Field(default_factory=list)


def _load_hla_config() -> dict:
    defaults = {
        "rti_type": "stub",
        "rti_host": "localhost",
        "rti_port": 11000,
        "federation_name": "S3M_Coalition",
        "fom_path": "configs/interop/s3m_fom.xml",
        "time_step_seconds": 0.1,
        "auto_bridge_dis": True,
    }
    path = Path("configs/interop-extended.yaml")
    if not path.exists():
        return defaults
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    section = payload.get("hla", {})
    if isinstance(section, dict):
        defaults.update(section)
    return defaults


hla_router = APIRouter()
_hla_adapter = HLAFederateAdapter(config=_load_hla_config())


@hla_router.post("/interop/hla/federation/create")
async def create_hla_federation(req: FederationCreateRequest) -> Dict[str, Any]:
    created = _hla_adapter.create_federation(name=req.name, fom_path=req.fom_path)
    if not created:
        raise HTTPException(status_code=400, detail="failed to create federation")
    return {"created": True, "status": _hla_adapter.get_federation_status()}


@hla_router.post("/interop/hla/federation/join")
async def join_hla_federation(req: FederationJoinRequest) -> Dict[str, Any]:
    joined = _hla_adapter.join_federation(name=req.name)
    if not joined:
        raise HTTPException(status_code=400, detail="failed to join federation")
    return {"joined": True, "status": _hla_adapter.get_federation_status()}


@hla_router.post("/interop/hla/federation/resign")
async def resign_hla_federation() -> Dict[str, Any]:
    resigned = _hla_adapter.resign_federation()
    if not resigned:
        raise HTTPException(status_code=400, detail="failed to resign federation")
    return {"resigned": True, "status": _hla_adapter.get_federation_status()}


@hla_router.post("/interop/hla/publish")
async def publish_hla_class(req: HLAPublishRequest) -> Dict[str, Any]:
    published = _hla_adapter.publish_object_class(class_name=req.class_name, attributes=req.attributes)
    if not published:
        raise HTTPException(status_code=400, detail="failed to publish object class")
    return {"published": True, "status": _hla_adapter.get_federation_status()}


@hla_router.get("/interop/hla/federation/status")
async def hla_federation_status() -> Dict[str, Any]:
    return _hla_adapter.get_federation_status()


@hla_router.get("/interop/hla/objects")
async def hla_objects() -> Dict[str, Any]:
    objects = _hla_adapter.get_objects()
    return {"objects": objects, "total": len(objects)}
