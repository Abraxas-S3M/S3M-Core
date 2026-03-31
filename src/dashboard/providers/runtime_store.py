"""Fallback in-memory tactical state for dashboard data providers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_DEFAULT_STATE: Dict[str, Any] = {
    "agents": [],
    "missions": [],
    "decisions": [],
    "formation": {"type": "UNKNOWN", "spacing": 0.0, "positions": {}, "score": 0.0},
    "last_swarm_command": None,
    "paths": [],
    "simulation": {"running_scenarios": 0, "replay_count": 0, "datasets_generated": 0},
    "jetson": {
        "gpu_util_pct": 0.0,
        "memory_pct": 0.0,
        "temperature_c": 0.0,
        "power_w": 0.0,
        "cuda_version": "unknown",
    },
    "edge_models": [],
    "gps": {
        "quality": "unknown",
        "satellites": 0,
        "mode": "unknown",
        "drift_m": 0.0,
        "last_fix": None,
    },
    "last_updated": _now_iso(),
}

_STATE: Dict[str, Any] = deepcopy(_DEFAULT_STATE)


def get_runtime_state() -> Dict[str, Any]:
    return _STATE


def reset_runtime_state() -> None:
    global _STATE
    _STATE = deepcopy(_DEFAULT_STATE)


def mark_updated() -> None:
    _STATE["last_updated"] = _now_iso()


def _set_list(key: str, values: List[Dict[str, Any]]) -> None:
    _STATE[key] = list(values)
    mark_updated()


def _set_dict(key: str, values: Dict[str, Any]) -> None:
    _STATE[key] = dict(values)
    mark_updated()


def set_agents(agents: List[Dict[str, Any]]) -> None:
    _set_list("agents", agents)


def set_missions(missions: List[Dict[str, Any]]) -> None:
    _set_list("missions", missions)


def set_decisions(decisions: List[Dict[str, Any]]) -> None:
    _set_list("decisions", decisions)


def set_paths(paths: List[Dict[str, Any]]) -> None:
    _set_list("paths", paths)


def set_formation(formation: Dict[str, Any]) -> None:
    _set_dict("formation", formation)


def set_last_swarm_command(command: Dict[str, Any]) -> None:
    _set_dict("last_swarm_command", command)


def set_simulation(simulation: Dict[str, Any]) -> None:
    _set_dict("simulation", simulation)


def set_jetson(jetson: Dict[str, Any]) -> None:
    _set_dict("jetson", jetson)


def set_edge_models(models: List[Dict[str, Any]]) -> None:
    _set_list("edge_models", models)


def set_gps(gps: Dict[str, Any]) -> None:
    _set_dict("gps", gps)


def set_threats(threats: List[Dict[str, Any]]) -> None:
    _set_list("threats", threats)


def set_sensors(sensors: List[Dict[str, Any]]) -> None:
    _set_list("sensors", sensors)
