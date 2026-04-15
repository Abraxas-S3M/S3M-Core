"""FastAPI routes for STANAG 4609 FMV metadata build/parse/registration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import yaml

from services.interop.fmv import FMVMetadataBuilder


class FMVMetadataBuildRequest(BaseModel):
    uav_status: dict[str, Any] = Field(default_factory=dict)
    payload_status: dict[str, Any] = Field(default_factory=dict)
    timestamp: float


class FMVMetadataParseRequest(BaseModel):
    metadata_packet_hex: str = Field(..., min_length=2)


class FMVRegisterRequest(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    video_reference: str = Field(..., min_length=1, max_length=512)


def _load_fmv_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "klv_standard": "MISB_0601",
        "embed_in_stream": False,
        "register_in_nsili": True,
    }
    path = Path("configs/interop-extended.yaml")
    if not path.exists():
        return defaults
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    fmv_cfg = payload.get("fmv")
    if isinstance(fmv_cfg, dict):
        defaults.update(fmv_cfg)
    return defaults


fmv_router = APIRouter()
_fmv_config = _load_fmv_config()
_builder = FMVMetadataBuilder(config=_fmv_config)


@fmv_router.post("/interop/fmv/metadata/build")
async def build_fmv_metadata(req: FMVMetadataBuildRequest) -> dict[str, Any]:
    try:
        packet = _builder.build_metadata_packet(req.uav_status, req.payload_status, req.timestamp)
        parsed = _builder.parse_metadata_packet(packet)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"metadata_packet_hex": packet.hex(), "metadata": parsed}


@fmv_router.post("/interop/fmv/metadata/parse")
async def parse_fmv_metadata(req: FMVMetadataParseRequest) -> dict[str, Any]:
    try:
        payload = bytes.fromhex(req.metadata_packet_hex.strip())
        parsed = _builder.parse_metadata_packet(payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return parsed


@fmv_router.post("/interop/fmv/register")
async def register_fmv(req: FMVRegisterRequest) -> dict[str, Any]:
    try:
        product_id = _builder.register_with_nsili(req.metadata, req.video_reference)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "product_id": product_id,
        "product_type": "VIDEO",
        "registered_in_nsili": bool(_fmv_config.get("register_in_nsili", True)),
    }


@fmv_router.get("/interop/fmv/status")
async def fmv_status() -> dict[str, Any]:
    return {
        "standard": _fmv_config.get("klv_standard", "MISB_0601"),
        "embed_in_stream": bool(_fmv_config.get("embed_in_stream", False)),
        "register_in_nsili": bool(_fmv_config.get("register_in_nsili", True)),
    }
