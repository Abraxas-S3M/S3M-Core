"""FastAPI routes for STANAG 4559 NSILI catalog interoperability."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
import yaml

from services.interop.registry import InteropRegistry
from services.interop.nsili import NSILICatalog, NSILIProductManager

nsili_router = APIRouter()

_STATE_LOCK = Lock()
_CATALOG: NSILICatalog | None = None
_MANAGER: NSILIProductManager | None = None
_REGISTRY = InteropRegistry()
_REGISTRY.register_capability(
    "nsili",
    "STANAG-4559-Ed3",
    [
        "local_catalog_query",
        "local_product_retrieval",
        "offline_xml_export",
        "partner_catalog_sync_phase1",
    ],
)


def _default_nsili_config() -> dict[str, Any]:
    return {
        "catalog_dir": "data/interop/nsili_catalog/",
        "max_products": 10000,
        "default_classification": "UNCLASSIFIED",
        "partner_catalogs": [],
    }


def _load_nsili_config() -> dict[str, Any]:
    config = _default_nsili_config()
    path = Path("configs/interop-extended.yaml")
    if not path.exists():
        return config

    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return config

    section = parsed.get("nsili", {}) if isinstance(parsed, dict) else {}
    if not isinstance(section, dict):
        return config

    catalog_dir = section.get("catalog_dir")
    if isinstance(catalog_dir, str) and catalog_dir.strip():
        config["catalog_dir"] = catalog_dir

    max_products = section.get("max_products")
    try:
        if max_products is not None:
            config["max_products"] = max(1, int(max_products))
    except (TypeError, ValueError):
        pass

    default_classification = section.get("default_classification")
    if isinstance(default_classification, str) and default_classification.strip():
        config["default_classification"] = default_classification.strip()

    partner_catalogs = section.get("partner_catalogs")
    if isinstance(partner_catalogs, list):
        config["partner_catalogs"] = [str(item).strip() for item in partner_catalogs if str(item).strip()]

    return config


_NSILI_CONFIG = _load_nsili_config()


def _ensure_manager() -> NSILIProductManager:
    global _CATALOG, _MANAGER
    with _STATE_LOCK:
        if _CATALOG is None:
            _CATALOG = NSILICatalog(config=_NSILI_CONFIG)
        if _MANAGER is None:
            _MANAGER = NSILIProductManager(catalog=_CATALOG)
    return _MANAGER


@nsili_router.get("/interop/nsili/catalog")
async def nsili_catalog_query(
    product_type: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    min_lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    min_lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    max_lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    max_lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    classification: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=10000),
) -> dict[str, Any]:
    manager = _ensure_manager()
    time_range = (start_time, end_time) if start_time or end_time else None
    bbox = None
    bbox_parts = [min_lat, min_lon, max_lat, max_lon]
    if any(part is not None for part in bbox_parts):
        if any(part is None for part in bbox_parts):
            raise HTTPException(
                status_code=400,
                detail="min_lat, min_lon, max_lat, and max_lon must be provided together",
            )
        bbox = (float(min_lat), float(min_lon), float(max_lat), float(max_lon))

    try:
        rows = manager.catalog.query(
            product_type=product_type,
            time_range=time_range,
            bbox=bbox,
            classification=classification,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"products": rows[:limit], "total": len(rows)}


@nsili_router.get("/interop/nsili/products/{product_id}")
async def nsili_get_product(product_id: str) -> dict[str, Any]:
    manager = _ensure_manager()
    try:
        product = manager.catalog.get_product(product_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return product


@nsili_router.post("/interop/nsili/products")
async def nsili_register_product(body: dict[str, Any]) -> dict[str, Any]:
    manager = _ensure_manager()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")

    try:
        if isinstance(body.get("productType"), str) and str(body.get("productType", "")).strip():
            product_id = manager.catalog.register_product(body)
        else:
            product_id = manager.ingest_intel_product(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"registered": True, "product_id": product_id}


@nsili_router.post("/interop/nsili/sync")
async def nsili_sync(body: dict[str, Any]) -> dict[str, Any]:
    manager = _ensure_manager()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    partner_url = str(body.get("partner_url", "")).strip()
    if not partner_url:
        raise HTTPException(status_code=400, detail="partner_url is required")

    imported = manager.sync_from_partner(partner_url=partner_url)
    return {"partner_url": partner_url, "imported": imported}


@nsili_router.get("/interop/nsili/export")
async def nsili_export_catalog() -> Response:
    manager = _ensure_manager()
    payload = manager.export_catalog_xml()
    return Response(content=payload, media_type="application/xml")


@nsili_router.get("/interop/nsili/status")
async def nsili_status() -> dict[str, Any]:
    manager = _ensure_manager()
    listing = manager.catalog.list_products(limit=1)
    return {
        "configured": True,
        "config": _NSILI_CONFIG,
        "catalog_dir": str(manager.catalog.catalog_dir),
        "catalog_count": len(manager.catalog.query()),
        "latest_product": listing[0] if listing else None,
        "registry": _REGISTRY.get_capabilities().get("nsili"),
    }
