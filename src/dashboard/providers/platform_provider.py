"""Platform dashboard provider for HOOL platform-state snapshots.

Military/tactical context:
This provider exposes near-real-time platform posture so operators can confirm
that autonomous assets remain healthy, maneuver-capable, and inside expected
command authority levels before issuing additional mission actions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from src.dashboard.providers.helpers import coerce_float, normalize_position
from src.dashboard.providers.runtime_store import get_runtime_state


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlatformProvider:
    """Provide platform-state snapshots compatible with dashboard WS publishing."""

    _VALID_AUTONOMY_LEVELS = {"manual", "supervised", "autonomous"}

    def __init__(self, adapters: Optional[Mapping[str, Any]] = None) -> None:
        self._runtime = get_runtime_state()
        self._adapters: Dict[str, Any] = {}
        self._adapter_autonomy: Dict[str, str] = {}
        for adapter_id, adapter in dict(adapters or {}).items():
            self.register_adapter(adapter_id=adapter_id, adapter=adapter)

    def register_adapter(self, adapter_id: str, adapter: Any, autonomy_level: str = "supervised") -> None:
        key = str(adapter_id or "").strip()
        if not key:
            raise ValueError("adapter_id must be a non-empty string")
        self._adapters[key] = adapter
        self._adapter_autonomy[key] = self._normalize_autonomy_level(autonomy_level)

    def unregister_adapter(self, adapter_id: str) -> None:
        key = str(adapter_id or "").strip()
        if not key:
            return
        self._adapters.pop(key, None)
        self._adapter_autonomy.pop(key, None)

    def _normalize_autonomy_level(self, value: Any) -> str:
        level = str(getattr(value, "value", value) or "supervised").strip().lower()
        if level in self._VALID_AUTONOMY_LEVELS:
            return level
        return "supervised"

    @staticmethod
    def _normalize_health(value: Any) -> str:
        raw = str(getattr(value, "value", value) or "unknown").strip().lower()
        if raw in {"nominal", "operational"}:
            return "nominal"
        if raw in {"degraded", "warning"}:
            return "degraded"
        if raw in {"fault", "critical", "destroyed"}:
            return "fault"
        return "unknown"

    @staticmethod
    def _safe_state_read(adapter: Any) -> Any:
        if adapter is None or not hasattr(adapter, "read_state"):
            return None
        try:
            return adapter.read_state()
        except Exception:
            return None

    def _row_from_adapter(self, adapter_id: str, adapter: Any) -> Dict[str, Any]:
        state = self._safe_state_read(adapter)
        position = normalize_position(getattr(state, "position", (0.0, 0.0, 0.0)))
        heading = coerce_float(getattr(state, "heading", getattr(adapter, "heading", 0.0)), 0.0)
        speed = coerce_float(getattr(state, "speed", getattr(adapter, "speed", 0.0)), 0.0)
        health = self._normalize_health(getattr(state, "health_state", getattr(state, "health", "unknown")))
        autonomy = self._normalize_autonomy_level(getattr(state, "autonomy_mode", self._adapter_autonomy.get(adapter_id)))
        platform_type = str(getattr(getattr(state, "platform_type", None), "value", getattr(state, "platform_type", "unknown")))
        return {
            "platform_id": adapter_id,
            "source": "adapter_registry",
            "platform_type": platform_type,
            "position": position,
            "heading": heading,
            "speed": speed,
            "health": health,
            "autonomy_level": autonomy,
        }

    def _row_from_swarm_agent(self, agent: Any) -> Dict[str, Any]:
        row = agent.to_dict() if hasattr(agent, "to_dict") else dict(getattr(agent, "__dict__", {}))
        health = "nominal"
        battery = coerce_float(row.get("battery_pct", row.get("battery", 100.0)), 100.0)
        comms = str(row.get("comms_status", "nominal")).lower()
        state = str(row.get("state", "active")).lower()
        if battery < 20.0 or comms == "degraded":
            health = "degraded"
        if state in {"destroyed", "lost"} or comms == "lost":
            health = "fault"
        autonomy_level = "autonomous" if state in {"active", "executing"} else "supervised"
        return {
            "platform_id": str(row.get("agent_id", row.get("id", "unknown"))),
            "source": "swarm_registry",
            "platform_type": str(row.get("capability", "unknown")),
            "position": normalize_position(row.get("position")),
            "heading": coerce_float(row.get("heading", 0.0), 0.0),
            "speed": coerce_float(row.get("speed", 0.0), 0.0),
            "health": health,
            "autonomy_level": autonomy_level,
        }

    def _rows_from_swarm_runtime(self) -> List[Dict[str, Any]]:
        try:
            from src.api.autonomy_routes import runtime

            return [self._row_from_swarm_agent(agent) for agent in runtime.coordinator.agents.values()]
        except Exception:
            return []

    def _rows_from_dashboard_runtime(self) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for item in self._runtime.get("agents", []):
            if not isinstance(item, dict):
                continue
            output.append(
                {
                    "platform_id": str(item.get("id", item.get("agent_id", "unknown"))),
                    "source": "dashboard_runtime",
                    "platform_type": str(item.get("capability", "unknown")),
                    "position": normalize_position(item.get("position")),
                    "heading": coerce_float(item.get("heading", 0.0), 0.0),
                    "speed": coerce_float(item.get("speed", 0.0), 0.0),
                    "health": self._normalize_health(item.get("health", item.get("health_state", "unknown"))),
                    "autonomy_level": self._normalize_autonomy_level(item.get("autonomy_level", "supervised")),
                }
            )
        return output

    def get_snapshot(self) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        for adapter_id, adapter in self._adapters.items():
            rows.append(self._row_from_adapter(adapter_id=adapter_id, adapter=adapter))

        if not rows:
            rows.extend(self._rows_from_swarm_runtime())
        if not rows:
            rows.extend(self._rows_from_dashboard_runtime())

        nominal = sum(1 for row in rows if row.get("health") == "nominal")
        degraded = sum(1 for row in rows if row.get("health") == "degraded")
        fault = sum(1 for row in rows if row.get("health") == "fault")

        return {
            "provider": "platform",
            "feed": "dashboard.platform.snapshot",
            "timestamp": _utcnow(),
            "platforms": rows,
            "summary": {
                "registered": len(rows),
                "nominal": nominal,
                "degraded": degraded,
                "fault": fault,
            },
        }
