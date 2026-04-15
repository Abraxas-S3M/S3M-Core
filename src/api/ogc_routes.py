"""FastAPI routes for OGC geospatial service interoperability."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
import yaml

from services.interop.ogc import GeoJSONAdapter, WFSClient, WMSClient

ogc_router = APIRouter()
_geojson_adapter = GeoJSONAdapter()


def _default_ogc_config() -> dict[str, Any]:
    return {
        "wms_servers": [],
        "wfs_servers": [],
        "default_srs": "EPSG:4326",
        "cache_dir": "data/interop/ogc_cache/",
    }


def _load_ogc_config() -> dict[str, Any]:
    config = _default_ogc_config()
    path = Path("configs/navigation.yaml")
    if not path.exists():
        return config
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return config

    section = payload.get("ogc", {}) if isinstance(payload, dict) else {}
    if not isinstance(section, dict):
        return config

    for key in ("wms_servers", "wfs_servers"):
        servers = section.get(key, config[key])
        if isinstance(servers, list):
            config[key] = servers

    default_srs = section.get("default_srs")
    if isinstance(default_srs, str) and default_srs.strip():
        config["default_srs"] = default_srs.strip()

    cache_dir = section.get("cache_dir")
    if isinstance(cache_dir, str) and cache_dir.strip():
        config["cache_dir"] = cache_dir.strip()

    return config


_OGC_CONFIG = _load_ogc_config()
Path(str(_OGC_CONFIG.get("cache_dir", "data/interop/ogc_cache/"))).mkdir(parents=True, exist_ok=True)


def _resolve_server_url(servers: list[Any], index: int) -> str:
    if index < 0 or index >= len(servers):
        raise HTTPException(status_code=404, detail=f"Server index out of range: {index}")
    server = servers[index]
    if isinstance(server, str):
        url = server.strip()
    elif isinstance(server, dict):
        url = str(server.get("url") or server.get("base_url") or "").strip()
    else:
        url = ""
    if not url:
        raise HTTPException(status_code=400, detail=f"Invalid server entry at index {index}")
    return url


@ogc_router.get("/interop/ogc/status")
async def ogc_status() -> dict[str, Any]:
    return {
        "configured": True,
        "default_srs": _OGC_CONFIG.get("default_srs"),
        "cache_dir": _OGC_CONFIG.get("cache_dir"),
        "wms_servers": _OGC_CONFIG.get("wms_servers", []),
        "wfs_servers": _OGC_CONFIG.get("wfs_servers", []),
        "wms_count": len(_OGC_CONFIG.get("wms_servers", [])),
        "wfs_count": len(_OGC_CONFIG.get("wfs_servers", [])),
    }


@ogc_router.get("/interop/ogc/wms/{server_index}/capabilities")
async def ogc_wms_capabilities(server_index: int) -> dict[str, Any]:
    url = _resolve_server_url(_OGC_CONFIG.get("wms_servers", []), server_index)
    client = WMSClient(url)
    return client.get_capabilities()


@ogc_router.get("/interop/ogc/wms/{server_index}/layers")
async def ogc_wms_layers(server_index: int) -> dict[str, Any]:
    url = _resolve_server_url(_OGC_CONFIG.get("wms_servers", []), server_index)
    client = WMSClient(url)
    rows = client.get_available_layers()
    return {"layers": rows, "total": len(rows)}


@ogc_router.post("/interop/ogc/wms/{server_index}/map")
async def ogc_wms_map(server_index: int, body: dict[str, Any]) -> dict[str, Any]:
    url = _resolve_server_url(_OGC_CONFIG.get("wms_servers", []), server_index)
    client = WMSClient(url)
    layers = body.get("layers", [])
    bbox = body.get("bbox")
    width = int(body.get("width", 1024))
    height = int(body.get("height", 1024))
    srs = str(body.get("srs") or _OGC_CONFIG.get("default_srs", "EPSG:4326"))
    image_format = str(body.get("format") or "image/png")
    try:
        image_bytes = client.get_map(
            layers=layers,
            bbox=tuple(bbox) if isinstance(bbox, list) else bbox,
            width=width,
            height=height,
            srs=srs,
            format=image_format,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "bytes": len(image_bytes),
        "empty": len(image_bytes) == 0,
        "srs": srs,
        "format": image_format,
    }


@ogc_router.get("/interop/ogc/wfs/{server_index}/capabilities")
async def ogc_wfs_capabilities(server_index: int) -> dict[str, Any]:
    url = _resolve_server_url(_OGC_CONFIG.get("wfs_servers", []), server_index)
    client = WFSClient(url)
    return client.get_capabilities()


@ogc_router.get("/interop/ogc/wfs/{server_index}/types")
async def ogc_wfs_types(server_index: int) -> dict[str, Any]:
    url = _resolve_server_url(_OGC_CONFIG.get("wfs_servers", []), server_index)
    client = WFSClient(url)
    rows = client.list_feature_types()
    return {"feature_types": rows, "total": len(rows)}


@ogc_router.post("/interop/ogc/wfs/{server_index}/feature")
async def ogc_wfs_feature(server_index: int, body: dict[str, Any]) -> dict[str, Any]:
    url = _resolve_server_url(_OGC_CONFIG.get("wfs_servers", []), server_index)
    client = WFSClient(url)
    type_name = str(body.get("type_name") or "").strip()
    if not type_name:
        raise HTTPException(status_code=400, detail="type_name is required")
    bbox = body.get("bbox")
    bbox_value = tuple(bbox) if isinstance(bbox, list) else bbox
    max_features = int(body.get("max_features", 100))
    try:
        payload = client.get_feature(type_name=type_name, bbox=bbox_value, max_features=max_features)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"type_name": type_name, "payload": payload, "empty": not bool(payload)}


@ogc_router.post("/interop/ogc/geojson/tracks")
async def ogc_tracks_to_geojson(body: dict[str, Any]) -> dict[str, Any]:
    tracks = body.get("tracks", [])
    try:
        return _geojson_adapter.tracks_to_geojson(tracks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ogc_router.post("/interop/ogc/geojson/mission")
async def ogc_mission_to_geojson(body: dict[str, Any]) -> dict[str, Any]:
    mission_layer = body.get("mission_layer", {})
    try:
        return _geojson_adapter.mission_to_geojson(mission_layer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ogc_router.post("/interop/ogc/geojson/to-tracks")
async def ogc_geojson_to_tracks(body: dict[str, Any]) -> dict[str, Any]:
    geojson = body.get("geojson", {})
    try:
        rows = _geojson_adapter.geojson_to_tracks(geojson)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"tracks": rows, "total": len(rows)}


@ogc_router.post("/interop/ogc/geojson/nvg-to-geojson")
async def ogc_nvg_to_geojson(body: dict[str, Any]) -> dict[str, Any]:
    nvg_parsed = body.get("nvg_parsed", {})
    try:
        return _geojson_adapter.nvg_to_geojson(nvg_parsed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ogc_router.post("/interop/ogc/geojson/to-nvg")
async def ogc_geojson_to_nvg(body: dict[str, Any]) -> dict[str, Any]:
    geojson = body.get("geojson", {})
    try:
        nvg_xml = _geojson_adapter.geojson_to_nvg(geojson)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"nvg_xml": nvg_xml}

