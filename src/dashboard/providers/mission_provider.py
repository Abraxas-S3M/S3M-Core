"""Mission dashboard provider for HOOL and autonomy command visibility.

Military/tactical context:
This provider surfaces mission phase progression and command queues so operators
can maintain command-and-control continuity during autonomous execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.dashboard.providers.runtime_store import get_runtime_state


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MissionProvider:
    """Provide mission status, phase timeline, and active command queue."""

    def __init__(self) -> None:
        self._runtime = get_runtime_state()

    @staticmethod
    def _as_iso(value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return _utcnow()
        return _utcnow()

    def _hool_missions(self) -> Dict[str, Dict[str, Any]]:
        try:
            from services.autonomy.hool_extension import api_routes

            rows = getattr(api_routes, "_MISSIONS", {})
            return rows if isinstance(rows, dict) else {}
        except Exception:
            return {}

    def _mission_phase_status(self) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []
        for mission_id, mission_row in self._hool_missions().items():
            if not isinstance(mission_row, dict):
                continue
            state = mission_row.get("state")
            output.append(
                {
                    "mission_id": str(getattr(state, "mission_id", mission_id)),
                    "status": str(mission_row.get("status", "unknown")),
                    "phase": str(getattr(state, "mode", "unknown")),
                    "platform_class": str(getattr(getattr(state, "platform_class", None), "value", "unknown")),
                    "risk_score": float(getattr(state, "risk_score", 0.0)),
                    "time_remaining_s": float(getattr(state, "time_remaining_s", 0.0)),
                    "started_at": self._as_iso(mission_row.get("started_at")),
                }
            )

        if output:
            return output

        for item in self._runtime.get("missions", []):
            if not isinstance(item, dict):
                continue
            output.append(
                {
                    "mission_id": str(item.get("id", item.get("mission_id", "unknown"))),
                    "status": str(item.get("status", "unknown")),
                    "phase": str(item.get("phase", item.get("mission_phase", "unknown"))),
                    "platform_class": str(item.get("platform_class", "unknown")),
                    "risk_score": float(item.get("risk_score", 0.0)),
                    "time_remaining_s": float(item.get("time_remaining_s", 0.0)),
                    "started_at": self._as_iso(item.get("started_at")),
                }
            )
        return output

    def _phase_transition_timeline(self) -> List[Dict[str, Any]]:
        timeline: List[Dict[str, Any]] = []
        for mission_id, mission_row in self._hool_missions().items():
            if not isinstance(mission_row, dict):
                continue
            agent = mission_row.get("agent")
            history = getattr(agent, "decision_history", [])
            if not isinstance(history, list):
                continue
            last_phase = ""
            for item in history:
                if not isinstance(item, dict):
                    continue
                context = item.get("context", {})
                phase = str(context.get("mode", "unknown")) if isinstance(context, dict) else "unknown"
                if phase == last_phase:
                    continue
                timeline.append(
                    {
                        "mission_id": str(item.get("mission_id", mission_id)),
                        "timestamp": self._as_iso(item.get("timestamp")),
                        "phase": phase,
                        "status": str(mission_row.get("status", "unknown")),
                        "reason": str(item.get("decision_type", "decision_update")).lower(),
                    }
                )
                last_phase = phase

        runtime_timeline = self._runtime.get("phase_transition_timeline", [])
        if isinstance(runtime_timeline, list):
            for item in runtime_timeline:
                if isinstance(item, dict):
                    timeline.append(dict(item))

        if not timeline:
            for mission in self._mission_phase_status():
                timeline.append(
                    {
                        "mission_id": str(mission.get("mission_id", "unknown")),
                        "timestamp": self._as_iso(mission.get("started_at")),
                        "phase": str(mission.get("phase", "unknown")),
                        "status": str(mission.get("status", "unknown")),
                        "reason": "current_state_snapshot",
                    }
                )

        timeline.sort(key=lambda row: str(row.get("timestamp", "")))
        return timeline

    @staticmethod
    def _serialize_command(command: Any) -> Dict[str, Any]:
        if hasattr(command, "to_dict"):
            try:
                data = command.to_dict()
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        if isinstance(command, dict):
            return dict(command)
        return {
            "command_id": str(getattr(command, "command_id", "unknown")),
            "command_type": str(getattr(getattr(command, "command_type", None), "value", "unknown")),
            "target_agents": list(getattr(command, "target_agents", [])),
            "issued_by": str(getattr(command, "issued_by", "unknown")),
            "issued_at": MissionProvider._as_iso(getattr(command, "issued_at", None)),
        }

    def _command_queue(self) -> List[Dict[str, Any]]:
        queue: List[Dict[str, Any]] = []
        try:
            from src.api.autonomy_routes import runtime

            for command in runtime.coordinator.command_queue:
                queue.append(self._serialize_command(command))
        except Exception:
            pass

        runtime_queue = self._runtime.get("command_queue", [])
        if isinstance(runtime_queue, list):
            for item in runtime_queue:
                if isinstance(item, dict):
                    queue.append(dict(item))
        if not queue:
            last_command = self._runtime.get("last_swarm_command")
            if isinstance(last_command, dict) and last_command:
                queue.append(dict(last_command))
        return queue

    def get_snapshot(self) -> Dict[str, Any]:
        mission_phase_status = self._mission_phase_status()
        timeline = self._phase_transition_timeline()
        command_queue = self._command_queue()
        return {
            "provider": "mission",
            "feed": "dashboard.mission.snapshot",
            "timestamp": _utcnow(),
            "mission_phase_status": mission_phase_status,
            "phase_transition_timeline": timeline,
            "command_queue": command_queue,
            "summary": {
                "missions": len(mission_phase_status),
                "timeline_events": len(timeline),
                "queue_depth": len(command_queue),
            },
        }
