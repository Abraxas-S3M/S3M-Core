"""Memory budget management for Jetson edge deployment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class _Component:
    name: str
    layer: str
    memory_mb: float
    priority: int
    loaded: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "layer": self.layer,
            "memory_mb": round(self.memory_mb, 2),
            "priority": self.priority,
            "loaded": self.loaded,
        }


class MemoryBudgetManager:
    """Track and enforce memory allocations across S3M layers.

    Tactical context:
    Keeping mission-critical layers resident prevents control-loop stalls during
    contested operations where restart windows are unavailable.
    """

    DEFAULT_ESTIMATES_MB: Dict[str, float] = {
        "llm_engine": 3000.0,
        "yolo": 200.0,
        "ekf_trackfuser": 50.0,
        "path_planner": 100.0,
        "swarm_coordinator": 50.0,
        "dashboard": 100.0,
        "builtin_physics": 200.0,
        "domain_app": 50.0,
    }

    def __init__(self, total_budget_gb: float = 48.0):
        if not isinstance(total_budget_gb, (int, float)) or float(total_budget_gb) <= 0:
            raise ValueError("total_budget_gb must be a positive number")
        self.total_budget_mb = float(total_budget_gb) * 1024.0
        self.registry: Dict[str, _Component] = {}

    def register(self, name: str, layer: str, estimated_memory_mb: float, priority: int = 5) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(layer, str) or not layer.strip():
            raise ValueError("layer must be a non-empty string")
        if not isinstance(estimated_memory_mb, (int, float)) or float(estimated_memory_mb) <= 0:
            raise ValueError("estimated_memory_mb must be a positive number")
        if not isinstance(priority, int) or priority <= 0:
            raise ValueError("priority must be a positive integer")

        self.registry[name] = _Component(
            name=name,
            layer=layer,
            memory_mb=float(estimated_memory_mb),
            priority=priority,
            loaded=self.registry.get(name, _Component(name, layer, float(estimated_memory_mb), priority)).loaded,
        )

    def _used_mb(self) -> float:
        return sum(component.memory_mb for component in self.registry.values() if component.loaded)

    def can_load(self, name: str) -> bool:
        component = self.registry.get(name)
        if component is None:
            raise ValueError(f"Unknown component: {name}")
        if component.loaded:
            return True
        return (self._used_mb() + component.memory_mb) <= self.total_budget_mb

    def mark_loaded(self, name: str) -> None:
        component = self.registry.get(name)
        if component is None:
            raise ValueError(f"Unknown component: {name}")
        component.loaded = True

    def mark_unloaded(self, name: str) -> None:
        component = self.registry.get(name)
        if component is None:
            raise ValueError(f"Unknown component: {name}")
        component.loaded = False

    def get_usage(self) -> dict:
        used = self._used_mb()
        available = max(0.0, self.total_budget_mb - used)
        utilization = 0.0 if self.total_budget_mb <= 0 else (used / self.total_budget_mb) * 100.0
        return {
            "total_budget_mb": round(self.total_budget_mb, 2),
            "used_mb": round(used, 2),
            "available_mb": round(available, 2),
            "utilization_pct": round(utilization, 2),
            "components": [component.to_dict() for component in sorted(self.registry.values(), key=lambda c: (c.priority, c.name))],
        }

    def suggest_eviction(self) -> Optional[str]:
        usage = self.get_usage()
        if usage["used_mb"] <= usage["total_budget_mb"]:
            return None

        loaded = [component for component in self.registry.values() if component.loaded]
        if not loaded:
            return None

        # Tactical rule: evict lowest-priority first; tie-break by highest memory impact.
        candidate = sorted(loaded, key=lambda c: (-c.priority, -c.memory_mb, c.name))[0]
        return candidate.name

    def auto_evict(self) -> List[str]:
        evicted: List[str] = []
        while self._used_mb() > self.total_budget_mb:
            name = self.suggest_eviction()
            if name is None:
                break
            self.mark_unloaded(name)
            evicted.append(name)
        return evicted

    def get_jetson_actual(self) -> dict:
        """Return actual memory telemetry when Jetson monitor is available.

        Falls back to estimate-only mode in non-Jetson development environments.
        """
        usage = self.get_usage()
        try:
            from src.navigation.edge.jetson_monitor import JetsonMonitor  # type: ignore

            monitor = JetsonMonitor()
            telemetry = monitor.get_memory_usage()
            return {
                "mode": "jetson_actual",
                "telemetry": telemetry,
                "estimated": usage,
            }
        except Exception:
            return {
                "mode": "estimated",
                "telemetry": None,
                "estimated": usage,
            }

    def generate_budget_report(self) -> str:
        usage = self.get_usage()
        lines = [
            "S3M MEMORY BUDGET REPORT",
            "Classification: UNCLASSIFIED - FOUO",
            f"Total Budget: {usage['total_budget_mb']:.2f} MB",
            f"Used:         {usage['used_mb']:.2f} MB",
            f"Available:    {usage['available_mb']:.2f} MB",
            f"Utilization:  {usage['utilization_pct']:.2f}%",
            "",
            "Registered Components:",
        ]
        for component in usage["components"]:
            lines.append(
                f"- [{ 'LOADED' if component['loaded'] else 'UNLOADED' }] "
                f"{component['name']} ({component['layer']}) "
                f"{component['memory_mb']:.2f} MB, priority={component['priority']}"
            )
        return "\n".join(lines)
