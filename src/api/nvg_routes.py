"""FastAPI routes for NATO Vector Graphics (NVG) overlay interoperability."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import yaml

from services.interop.nvg import NVGOverlayExchange
from src.api.gui_bridge.adapters.cop_adapter import COPAdapter

nvg_router = APIRouter()
_cop_adapter = COPAdapter()


def _load_nvg_config() -> dict:
    defaults = {
        "version": "2.0",
        "namespace": "http://tide.act.nato.int/schemas/2012/10/nvg",
        "publish_interval_seconds": 10,
        "outbox_dir": "data/interop/nvg_outbox/",
    }
    config_path = Path("configs/interop-extended.yaml")
    if not config_path.exists():
        return defaults
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return defaults
    nvg_cfg = payload.get("nvg", {})
    if isinstance(nvg_cfg, dict):
        defaults.update(nvg_cfg)
    return defaults


_nvg_exchange = NVGOverlayExchange(config=_load_nvg_config())


class NVGCopPublishRequest(BaseModel):
    tracks: List[Dict[str, Any]] | None = None
    mission_layers: List[Dict[str, Any]] | Dict[str, Any] | None = None


class NVGOverlayPublishRequest(BaseModel):
    mission_layer: Dict[str, Any] = Field(default_factory=dict)


class NVGImportRequest(BaseModel):
    xml: str = Field(..., min_length=1)


@nvg_router.post("/interop/nvg/publish/cop")
async def publish_cop_overlay(req: NVGCopPublishRequest) -> Dict[str, Any]:
    tracks: List[Dict[str, Any]]
    if req.tracks is None:
        tracks = _cop_adapter.get_tracks().model_dump().get("tracks", [])
    else:
        tracks = req.tracks

    if req.mission_layers is None:
        mission_layers: List[Dict[str, Any]] = [_cop_adapter.get_mission_overlay()]
    else:
        mission_layers = req.mission_layers
    try:
        xml = _nvg_exchange.publish_cop_overlay(tracks=tracks, mission_layers=mission_layers)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"failed to publish NVG COP overlay: {exc}") from exc
    return {"published_tracks": len(tracks), "xml": xml, "status": _nvg_exchange.status()}


@nvg_router.post("/interop/nvg/publish/overlay")
async def publish_operational_overlay(req: NVGOverlayPublishRequest) -> Dict[str, Any]:
    try:
        xml = _nvg_exchange.publish_operational_overlay(req.mission_layer)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"failed to publish NVG overlay: {exc}") from exc
    return {"xml": xml, "status": _nvg_exchange.status()}


@nvg_router.post("/interop/nvg/import")
async def import_nvg_overlay(req: NVGImportRequest) -> Dict[str, Any]:
    try:
        received = _nvg_exchange.receive_overlay(req.xml)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"failed to parse NVG XML: {exc}") from exc
    return {
        "tracks": received["tracks"],
        "mission_layer": received["mission_layer"],
        "counts": {
            "tracks": len(received["tracks"]),
            "polylines": len(received["parsed"].get("polylines", [])),
            "polygons": len(received["parsed"].get("polygons", [])),
            "circles": len(received["parsed"].get("circles", [])),
        },
    }


@nvg_router.get("/interop/nvg/export/cop")
async def export_current_cop_nvg_file() -> Response:
    tracks = _cop_adapter.get_tracks().model_dump().get("tracks", [])
    mission_layer = _cop_adapter.get_mission_overlay()
    try:
        path = _nvg_exchange.export_current_cop_file(tracks=tracks, mission_layers=[mission_layer])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to export NVG file: {exc}") from exc

    xml = path.read_text(encoding="utf-8")
    filename = path.name
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=xml, media_type="application/xml", headers=headers)


@nvg_router.get("/interop/nvg/status")
async def nvg_status() -> Dict[str, Any]:
    return _nvg_exchange.status()

