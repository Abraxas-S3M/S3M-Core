"""System status route for S3M-GUI health and engine visibility."""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter

system_router = APIRouter(prefix="/system", tags=["GUI System"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collect_engine_status() -> Dict[str, Dict[str, Any]]:
    engines: Dict[str, Dict[str, Any]] = {}
    try:
        from src.llm_core.engine_registry import EngineRegistry

        registry = EngineRegistry()
        configs = registry.get_all_engines()
        live_status = registry.get_status() if hasattr(registry, "get_status") else {}
        for cfg in configs:
            engine_id = getattr(getattr(cfg, "engine_id", None), "value", None) or cfg.name
            engines[str(engine_id)] = {
                "loaded": bool(live_status.get(engine_id, getattr(cfg, "loaded", False))),
                "name": cfg.name,
            }
    except Exception:
        return {}
    return engines


def _collect_uptime_seconds() -> int:
    try:
        from src.dashboard.aggregator import DashboardAggregator

        overview = DashboardAggregator().get_overview()
        uptime = overview.get("system", {}).get("uptime_seconds", 0)
        return int(float(uptime))
    except Exception:
        return 0


@system_router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    return {
        "status": "operational",
        "engines": _collect_engine_status(),
        "uptime": _collect_uptime_seconds(),
        "version": "0.2.0",
        "updatedAt": _now_iso(),
    }
