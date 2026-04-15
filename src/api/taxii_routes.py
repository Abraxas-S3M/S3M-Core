"""FastAPI routes for STIX/TAXII cyber threat intelligence exchange."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
import yaml

from services.interop.registry import InteropRegistry
from services.interop.stix import STIXTAXIIBridge, TAXIIClient
from src.apps.intel.stix_processor import STIXProcessor

taxii_router = APIRouter()

_STATE_LOCK = Lock()
_BRIDGE: STIXTAXIIBridge | None = None
_REGISTRY = InteropRegistry()
_REGISTRY.register_capability(
    "taxii",
    "2.1",
    [
        "stix_bundle_publish",
        "stix_bundle_poll",
        "offline_outbox_queue",
        "offline_inbox_cache",
    ],
)


def _default_taxii_config() -> dict[str, Any]:
    return {
        "servers": [],
        "poll_interval_seconds": 300,
        "outbox_dir": "data/interop/taxii_outbox/",
        "inbox_dir": "data/interop/taxii_inbox/",
        "auto_contribute": False,
    }


def _load_taxii_config() -> dict[str, Any]:
    config = _default_taxii_config()
    path = Path("configs/interop-extended.yaml")
    if not path.exists():
        return config
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return config

    section = parsed.get("taxii", {}) if isinstance(parsed, dict) else {}
    if not isinstance(section, dict):
        return config

    servers = section.get("servers", [])
    if isinstance(servers, list):
        config["servers"] = [item for item in servers if isinstance(item, dict)]
    try:
        config["poll_interval_seconds"] = max(1, int(section.get("poll_interval_seconds", config["poll_interval_seconds"])))
    except (TypeError, ValueError):
        pass
    outbox = section.get("outbox_dir")
    if isinstance(outbox, str) and outbox.strip():
        config["outbox_dir"] = outbox
    inbox = section.get("inbox_dir")
    if isinstance(inbox, str) and inbox.strip():
        config["inbox_dir"] = inbox
    config["auto_contribute"] = bool(section.get("auto_contribute", config["auto_contribute"]))
    return config


_TAXII_CONFIG = _load_taxii_config()


def _bridge_or_400() -> STIXTAXIIBridge:
    if _BRIDGE is None:
        raise HTTPException(status_code=400, detail="TAXII client not configured. Call /interop/taxii/connect first.")
    return _BRIDGE


def _build_bridge(server_url: str, collection_id: str | None, auth: dict | None) -> STIXTAXIIBridge:
    client = TAXIIClient(
        server_url=server_url,
        collection_id=collection_id,
        auth=auth,
        outbox_dir=str(_TAXII_CONFIG["outbox_dir"]),
        inbox_dir=str(_TAXII_CONFIG["inbox_dir"]),
    )
    bridge = STIXTAXIIBridge(taxii_client=client, stix_processor=STIXProcessor())
    return bridge


if _TAXII_CONFIG["servers"]:
    first = _TAXII_CONFIG["servers"][0]
    if isinstance(first, dict) and str(first.get("server_url", "")).strip():
        _BRIDGE = _build_bridge(
            server_url=str(first.get("server_url", "")).strip(),
            collection_id=str(first.get("collection_id", "")).strip() or None,
            auth=first.get("auth") if isinstance(first.get("auth"), dict) else None,
        )
        poll_interval = int(_TAXII_CONFIG.get("poll_interval_seconds", 300))
        if poll_interval > 0 and _BRIDGE.taxii_client.collection_id:
            _BRIDGE.schedule_polling(poll_interval)


@taxii_router.post("/interop/taxii/connect")
async def taxii_connect(body: dict[str, Any]) -> Dict[str, Any]:
    server_url = str(body.get("server_url", "")).strip()
    if not server_url:
        raise HTTPException(status_code=400, detail="server_url is required")

    collection_id = str(body.get("collection_id", "")).strip() or None
    auth = body.get("auth", {})
    if auth is not None and not isinstance(auth, dict):
        raise HTTPException(status_code=400, detail="auth must be an object")
    auth_dict = auth if isinstance(auth, dict) else None

    with _STATE_LOCK:
        global _BRIDGE
        _BRIDGE = _build_bridge(server_url=server_url, collection_id=collection_id, auth=auth_dict)

    discovery: dict[str, Any]
    try:
        discovery = _BRIDGE.taxii_client.discover()
    except Exception as exc:
        discovery = {"api_roots": [], "error": str(exc)}
    poll_interval = int(_TAXII_CONFIG.get("poll_interval_seconds", 300))
    if poll_interval > 0 and _BRIDGE.taxii_client.collection_id:
        _BRIDGE.schedule_polling(poll_interval)

    status = _BRIDGE.get_sync_status()
    return {
        "connected": bool(status["taxii_transport"].get("connected")),
        "discovery": discovery,
        "status": status,
    }


@taxii_router.post("/interop/taxii/poll")
async def taxii_poll(body: dict[str, Any] | None = None) -> Dict[str, Any]:
    bridge = _bridge_or_400()
    payload = body or {}
    collection_id = str(payload.get("collection_id", "")).strip() or None
    try:
        result = bridge.sync_feed(collection_id=collection_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@taxii_router.post("/interop/taxii/contribute")
async def taxii_contribute(body: dict[str, Any]) -> Dict[str, Any]:
    bridge = _bridge_or_400()
    watchlist_name = str(body.get("watchlist_name", "")).strip()
    if not watchlist_name:
        raise HTTPException(status_code=400, detail="watchlist_name is required")

    collection_id = str(body.get("collection_id", "")).strip()
    if collection_id:
        bridge.taxii_client.collection_id = collection_id

    try:
        contributed = bridge.contribute_watchlist(watchlist_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"contributed": contributed, "status": bridge.get_sync_status()}


@taxii_router.get("/interop/taxii/status")
async def taxii_status() -> Dict[str, Any]:
    if _BRIDGE is None:
        return {
            "configured": False,
            "config": _TAXII_CONFIG,
            "registry": _REGISTRY.get_capabilities().get("taxii"),
        }
    return {
        "configured": True,
        "sync": _BRIDGE.get_sync_status(),
        "config": _TAXII_CONFIG,
        "registry": _REGISTRY.get_capabilities().get("taxii"),
    }


@taxii_router.get("/interop/taxii/collections")
async def taxii_collections(api_root: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    bridge = _bridge_or_400()
    try:
        rows = bridge.taxii_client.list_collections(api_root=api_root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"collections": rows, "total": len(rows)}
