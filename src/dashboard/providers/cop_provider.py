"""COP data provider for Layer 06 dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.dashboard.providers.helpers import normalize_position, to_dict
from src.dashboard.providers.runtime_store import get_runtime_state


class COPDataProvider:
    """Common Operating Picture provider with tactical safe defaults."""

    ICON_TYPE_MAP = {
        "LEADER": "star",
        "SCOUT": "eye",
        "INTERCEPTOR": "crosshair",
        "FOLLOWER": "circle",
    }

    THREAT_COLOR_MAP = {
        "CRITICAL": "#ff0000",
        "HIGH": "#ff6600",
        "MEDIUM": "#ffcc00",
        "LOW": "#00cc00",
        "INFO": "#0088ff",
    }

    def __init__(self) -> None:
        self._runtime = get_runtime_state()
        self._swarm_cls = None
        self._threat_cls = None
        self._threat_manager = None
        self._sensor_manager = None
        self._track_fuser_cls = None
        self._planning_cls = None
        self._formation_cls = None
        self._load_optionals()

    def _load_optionals(self) -> None:
        try:
            from src.autonomy.swarm.coordinator import SwarmCoordinator  # type: ignore

            self._swarm_cls = SwarmCoordinator
        except Exception:
            self._swarm_cls = None

        try:
            from src.autonomy.swarm.formation_controller import FormationController  # type: ignore

            self._formation_cls = FormationController
        except Exception:
            self._formation_cls = None

        try:
            from src.threat_detection.threat_manager import ThreatManager

            self._threat_cls = ThreatManager
        except Exception:
            self._threat_cls = None

        # Prefer shared in-process managers used by API routes.
        try:
            from src.api import threat_routes

            self._threat_manager = getattr(threat_routes, "_threat_manager", None)
            self._sensor_manager = getattr(threat_routes, "_sensor_manager", None)
        except Exception:
            self._threat_manager = None
            self._sensor_manager = None

        try:
            from src.sensor_fusion.track_fuser import TrackFuser

            self._track_fuser_cls = TrackFuser
        except Exception:
            self._track_fuser_cls = None

        try:
            from src.navigation.planning.manager import PlanningManager  # type: ignore

            self._planning_cls = PlanningManager
        except Exception:
            self._planning_cls = None

    def _safe_instance(self, cls: Any) -> Any:
        if cls is None:
            return None
        try:
            return cls()
        except Exception:
            return None

    def get_cop_data(self) -> Dict[str, Any]:
        return {
            "agents": self.get_agents(),
            "threats": self.get_threats(),
            "tracks": self.get_tracks(),
            "paths": self.get_paths(),
            "formations": self.get_formations(),
            "terrain": {
                "type": "desert_flat",
                "name": "default_training_range",
                "obstacles": [],
            },
            "bounds": {"x": [0, 1000], "y": [0, 1000], "z": [0, 200]},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_agents(self) -> List[Dict[str, Any]]:
        swarm = self._safe_instance(self._swarm_cls)
        if swarm is None:
            return self._agents_from_runtime()

        try:
            raw_agents = swarm.get_agents()
        except Exception:
            return self._agents_from_runtime()

        agents: List[Dict[str, Any]] = []
        for agent in raw_agents if isinstance(raw_agents, list) else []:
            data = to_dict(agent)
            role = str(data.get("role", "UNKNOWN")).upper()
            agents.append(
                {
                    "id": str(data.get("id", data.get("agent_id", "unknown"))),
                    "role": role,
                    "state": str(data.get("state", "UNKNOWN")),
                    "position": normalize_position(data.get("position")),
                    "heading": float(data.get("heading", 0.0) or 0.0),
                    "battery": float(data.get("battery", data.get("battery_pct", 0.0)) or 0.0),
                    "capability": str(data.get("capability", "general")),
                    "icon_type": self.ICON_TYPE_MAP.get(role, "triangle"),
                }
            )
        return agents

    def _agents_from_runtime(self) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for item in self._runtime.get("agents", []):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "UNKNOWN")).upper()
            output.append(
                {
                    "id": str(item.get("id", "unknown")),
                    "role": role,
                    "state": str(item.get("state", "UNKNOWN")),
                    "position": normalize_position(item.get("position")),
                    "heading": float(item.get("heading", 0.0) or 0.0),
                    "battery": float(item.get("battery", 0.0) or 0.0),
                    "capability": str(item.get("capability", "general")),
                    "icon_type": self.ICON_TYPE_MAP.get(role, "triangle"),
                }
            )
        return output

    def get_threats(self) -> List[Dict[str, Any]]:
        manager = self._threat_manager
        if self._threat_cls is not None:
            manager = self._safe_instance(self._threat_cls)
        if manager is None:
            manager = self._threat_manager
        if manager is None:
            return []
        try:
            events = manager.get_threats(limit=100)
        except Exception:
            return []

        output: List[Dict[str, Any]] = []
        for event in events if isinstance(events, list) else []:
            data = to_dict(event)
            level = str(data.get("level", "INFO")).upper()
            output.append(
                {
                    "id": str(data.get("event_id", data.get("id", "unknown"))),
                    "level": level,
                    "category": str(data.get("category", "UNKNOWN")),
                    "position": normalize_position(data.get("location", data.get("position"))),
                    "title": str(data.get("title", "Threat event")),
                    "timestamp": str(data.get("timestamp", datetime.now(timezone.utc).isoformat())),
                    "confidence": float(data.get("confidence", 0.0) or 0.0),
                    "color": self.THREAT_COLOR_MAP.get(level, "#0088ff"),
                }
            )
        return output

    def get_tracks(self) -> List[Dict[str, Any]]:
        tracks: List[Any] = []
        if self._sensor_manager is not None and hasattr(self._sensor_manager, "get_fused_tracks"):
            try:
                tracks = self._sensor_manager.get_fused_tracks()
            except Exception:
                tracks = []
        if not tracks:
            fuser = self._safe_instance(self._track_fuser_cls)
            if fuser is None:
                return []
            try:
                tracks = fuser.get_tracks()
            except Exception:
                return []

        output: List[Dict[str, Any]] = []
        for track in tracks if isinstance(tracks, list) else []:
            data = to_dict(track)
            output.append(
                {
                    "id": str(data.get("track_id", "unknown")),
                    "state": str(data.get("state", "UNKNOWN")),
                    "position": normalize_position(data.get("position")),
                    "velocity": normalize_position(data.get("velocity")),
                    "confidence": float(data.get("confidence", 0.0) or 0.0),
                    "classification": data.get("classification"),
                    "last_update": str(data.get("last_update", datetime.now(timezone.utc).isoformat())),
                }
            )
        return output

    def get_paths(self) -> List[Dict[str, Any]]:
        planner = self._safe_instance(self._planning_cls)
        if planner is None:
            paths = self._runtime.get("paths", [])
            return list(paths) if isinstance(paths, list) else []

        try:
            active_paths = planner.get_active_paths()
        except Exception:
            paths = self._runtime.get("paths", [])
            return list(paths) if isinstance(paths, list) else []

        output: List[Dict[str, Any]] = []
        for path in active_paths if isinstance(active_paths, list) else []:
            data = to_dict(path)
            points = data.get("waypoints", [])
            output.append(
                {
                    "path_id": str(data.get("path_id", "unknown")),
                    "agent_id": str(data.get("agent_id", "unknown")),
                    "waypoints": [normalize_position(p) for p in points if isinstance(points, list)],
                    "status": str(data.get("status", "unknown")),
                }
            )
        return output

    def get_formations(self) -> Dict[str, Any]:
        controller = self._safe_instance(self._formation_cls)
        if controller is None:
            formation = self._runtime.get("formation", {})
            return dict(formation) if isinstance(formation, dict) else {}
        try:
            if hasattr(controller, "get_formation_status"):
                data = controller.get_formation_status()
                return dict(data) if isinstance(data, dict) else {}
        except Exception:
            pass
        formation = self._runtime.get("formation", {})
        return dict(formation) if isinstance(formation, dict) else {}

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "detail": "cop provider ready",
            "imports": {
                "autonomy_swarm": self._swarm_cls is not None,
                "threat_manager": self._threat_cls is not None,
                "track_fuser": self._track_fuser_cls is not None,
                "planning_manager": self._planning_cls is not None,
                "formation_controller": self._formation_cls is not None,
            },
        }
