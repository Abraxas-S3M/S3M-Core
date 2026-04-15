"""FastAPI routes for NFFI coalition friendly-force exchange."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field
import yaml

from services.interop.nffi import NFFIGateway, NFFIMessageBuilder


class NFFIConnectRequest(BaseModel):
    gateway_url: Optional[str] = None


class NFFIPublishRequest(BaseModel):
    tracks: List[Dict[str, Any]] = Field(default_factory=list)


def _load_nffi_config() -> dict:
    defaults = {
        "transport_profile": "IP-1",
        "gateway_url": None,
        "publish_interval_seconds": 10,
        "track_source_country": "SAU",
        "system_id": "S3M-FALCON",
        "outbox_dir": "data/interop/nffi_outbox/",
        "stale_threshold_seconds": 300,
    }
    path = Path("configs/interop-extended.yaml")
    if not path.exists():
        return defaults
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    nffi_cfg = payload.get("nffi", {})
    if isinstance(nffi_cfg, dict):
        defaults.update(nffi_cfg)
    return defaults


nffi_router = APIRouter()
_nffi_gateway = NFFIGateway(config=_load_nffi_config(), message_builder=NFFIMessageBuilder())


@nffi_router.post("/interop/nffi/connect")
async def connect_nffi(req: NFFIConnectRequest | None = None) -> Dict[str, Any]:
    connected = _nffi_gateway.connect(req.gateway_url if req else None)
    return {"connected": connected, "status": _nffi_gateway.health_check()}


@nffi_router.post("/interop/nffi/disconnect")
async def disconnect_nffi() -> Dict[str, Any]:
    _nffi_gateway.disconnect()
    return {"connected": False, "status": _nffi_gateway.health_check()}


@nffi_router.post("/interop/nffi/publish")
async def publish_nffi(req: NFFIPublishRequest) -> Dict[str, Any]:
    published = _nffi_gateway.publish_friendly_tracks(req.tracks)
    return {"published_tracks": published, "status": _nffi_gateway.health_check()}


@nffi_router.get("/interop/nffi/tracks")
async def receive_nffi_tracks() -> Dict[str, Any]:
    tracks = _nffi_gateway.receive_coalition_tracks()
    return {"tracks": tracks, "count": len(tracks)}


@nffi_router.get("/interop/nffi/status")
async def nffi_status() -> Dict[str, Any]:
    return _nffi_gateway.health_check()
