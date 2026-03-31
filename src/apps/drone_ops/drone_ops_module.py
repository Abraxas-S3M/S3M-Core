"""End-to-end drone operations module for Phase 11."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.apps.drone_ops.atr_integrator import ATRIntegrator
from src.apps.drone_ops.autopilot_bridge import AutopilotBridge
from src.apps.drone_ops.mission_planner import MissionPlanner
from src.apps._shared import ensure_non_empty_text, utc_now_iso


class DroneOpsModule:
    """Orchestrate mission planning, autopilot bridge, and ATR pipeline."""

    def __init__(self) -> None:
        self.mission_planner = MissionPlanner()
        self.autopilot = AutopilotBridge(backend="auto")
        self.atr = ATRIntegrator()
        self._active_missions: set[str] = set()

    def launch_mission(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise ValueError("request must be a dictionary")
        plan = self.mission_planner.plan_mission(request)
        connection = self.autopilot.connect()
        if connection:
            self._active_missions.add(plan["mission_id"])
        return {
            "mission": plan,
            "autopilot_connected": connection,
            "timestamp": utc_now_iso(),
        }

    def launch_from_nl(self, text: str, language: str = "en") -> dict:
        ensure_non_empty_text(text, "text")
        plan = self.mission_planner.plan_from_nl(text, language=language)
        launched = self.launch_mission(
            {
                "mission_type": plan["mission_type"],
                "waypoints": plan["waypoints"],
                "num_agents": max(1, len(plan.get("agents_assigned", {}))),
                "rules_of_engagement": "weapons_tight",
                "description": text,
            }
        )
        launched["parsed_plan"] = plan
        return launched

    def get_active_missions(self) -> List[dict]:
        missions = self.mission_planner.get_missions()
        return [mission for mission in missions if mission.get("mission_id") in self._active_missions]

    def abort(self, mission_id: str) -> dict:
        ensure_non_empty_text(mission_id, "mission_id")
        self.mission_planner.abort_mission(mission_id)
        self._active_missions.discard(mission_id)
        self.autopilot.send_command({"type": "EMERGENCY_STOP"})
        return {"mission_id": mission_id, "status": "aborted", "timestamp": utc_now_iso()}

    def process_camera_frame(self, image_path, agent_position: Optional[tuple] = None) -> dict:
        result = self.atr.process_frame(image_path, agent_position=agent_position)
        return {
            "atr": result,
            "replan_recommended": bool(result.get("replan_recommended", False)),
            "timestamp": utc_now_iso(),
        }

    def get_fleet_status(self) -> dict:
        telemetry = self.autopilot.get_telemetry()
        return {
            "missions": self.get_active_missions(),
            "telemetry": telemetry,
            "planner_stats": {"total_missions": len(self.mission_planner.get_missions())},
            "timestamp": utc_now_iso(),
        }

    def health_check(self) -> dict:
        return {
            "module": "drone_ops",
            "planner": {"status": "ready", "missions": len(self.mission_planner.get_missions())},
            "autopilot": self.autopilot.health_check(),
            "atr": self.atr.get_stats(),
            "active_missions": len(self._active_missions),
            "timestamp": utc_now_iso(),
        }

