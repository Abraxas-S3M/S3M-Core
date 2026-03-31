"""System-wide health provider for dashboard readiness monitoring."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.dashboard.providers.runtime_store import get_runtime_state


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SystemHealthProvider:
    """Collect Layer 01-06 tactical status with secure fallback defaults."""

    def __init__(self) -> None:
        self._start_time = time.time()

    def _layer_status(self, module_path: str, class_name: str) -> Dict[str, str]:
        try:
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            _instance = cls()
            return {"status": "operational", "detail": "available"}
        except Exception as exc:
            return {"status": "unavailable", "detail": f"{class_name} unavailable: {exc}"}

    def get_system_health(self) -> Dict[str, Any]:
        layers = {
            "llm_core": self._layer_status("src.llm_core.engine_registry", "EngineRegistry"),
            "threat_detection": self._layer_status("src.threat_detection.threat_manager", "ThreatManager"),
            "autonomy": self._layer_status("src.autonomy.swarm.coordinator", "SwarmCoordinator"),
            "simulation": self._layer_status("src.simulation.wargame.scenario_runner", "ScenarioRunner"),
            "navigation": self._layer_status("src.navigation.localization.manager", "LocalizationManager"),
            "dashboard": {"status": "operational", "detail": "running"},
        }
        status_rank = {"operational": 0, "degraded": 1, "critical": 2, "unavailable": 2}
        worst = max(status_rank.get(layer.get("status", "degraded"), 1) for layer in layers.values())
        overall_status = "operational" if worst == 0 else ("degraded" if worst == 1 else "critical")

        api_health = self.get_api_health()
        return {
            "overall_status": overall_status,
            "layers": layers,
            "uptime_seconds": int(max(0.0, time.time() - self._start_time)),
            "total_api_endpoints": int(api_health["healthy"] + api_health["unhealthy"]),
            "api_health": api_health,
            "timestamp": _utcnow(),
        }

    def get_jetson_stats(self) -> Dict[str, Any]:
        runtime = get_runtime_state().get("jetson", {})
        defaults = {
            "gpu_util_pct": 0.0,
            "memory_pct": 0.0,
            "temperature_c": 0.0,
            "power_w": 0.0,
            "cuda_version": "unknown",
            "status": "simulated",
        }
        payload = dict(defaults)
        if isinstance(runtime, dict):
            payload.update(runtime)
        if os.path.exists("/usr/bin/tegrastats"):
            payload["status"] = "available"
        return payload

    def get_edge_models(self) -> List[Dict[str, Any]]:
        runtime_models = get_runtime_state().get("edge_models", [])
        if isinstance(runtime_models, list):
            return [item for item in runtime_models if isinstance(item, dict)]
        return []

    def get_gps_status(self) -> Dict[str, Any]:
        runtime = get_runtime_state().get("gps", {})
        defaults = {
            "quality": "unknown",
            "satellites": 0,
            "mode": "unknown",
            "drift_m": 0.0,
            "last_fix": None,
        }
        payload = dict(defaults)
        if isinstance(runtime, dict):
            payload.update(runtime)
        return payload

    def get_simulation_status(self) -> Dict[str, Any]:
        runtime = get_runtime_state().get("simulation", {})
        defaults = {
            "running_scenarios": 0,
            "replay_count": 0,
            "datasets_generated": 0,
            "status": "idle",
        }
        payload = dict(defaults)
        if isinstance(runtime, dict):
            payload.update(runtime)
        return payload

    def get_api_health(self) -> Dict[str, int]:
        targets = ["/health", "/engines", "/threats", "/autonomy", "/simulation", "/navigation"]
        healthy = 0
        unhealthy = 0
        try:
            from src.api.server import app

            route_paths = {getattr(route, "path", "") for route in app.routes}
            for prefix in targets:
                if any(path == prefix or path.startswith(f"{prefix}/") for path in route_paths):
                    healthy += 1
                else:
                    unhealthy += 1
        except Exception:
            unhealthy = len(targets)
        return {"healthy": healthy, "unhealthy": unhealthy}

    def health_check(self) -> Dict[str, str]:
        return {"status": "operational", "detail": "system health provider active"}
