"""Autonomy dashboard provider for Layer 03 mission operations."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.dashboard.providers.helpers import (
    as_dict,
    clamp,
    coerce_float,
    coerce_int,
    coerce_position,
    parse_iso_time,
    utc_now_iso,
)
from src.dashboard.providers.runtime_store import (
    get_runtime_state,
    mark_updated,
    set_decisions,
    set_last_swarm_command,
)


class AutonomyDashProvider:
    """Expose autonomy agents, missions, decisions, and review workflow."""

    def __init__(self) -> None:
        self._runtime = get_runtime_state()
        self._swarm = self._build_optional("src.autonomy.swarm.coordinator", "SwarmCoordinator")
        self._explainer = self._build_optional("src.autonomy.xai.decision_explainer", "DecisionExplainer")

    @property
    def active(self) -> bool:
        return self._swarm is not None

    @staticmethod
    def _build_optional(module_path: str, class_name: str) -> Any:
        try:
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            return cls()
        except Exception:
            return None

    def get_agent_roster(self) -> List[Dict[str, Any]]:
        agents: List[Dict[str, Any]] = []
        if self._swarm is not None and hasattr(self._swarm, "get_agents"):
            try:
                for entry in self._swarm.get_agents():
                    agents.append(as_dict(entry))
            except Exception:
                agents = []
        if not agents:
            agents = [dict(item) for item in self._runtime.get("agents", []) if isinstance(item, dict)]

        formation = self.get_formation_data()
        formation_positions = formation.get("positions", {})
        now = datetime.now(timezone.utc)
        out: List[Dict[str, Any]] = []
        for index, agent in enumerate(agents):
            agent_id = str(agent.get("id", agent.get("agent_id", f"agent-{index+1}")))
            heartbeat = parse_iso_time(agent.get("last_heartbeat"))
            delta = 0.0 if heartbeat is None else max(0.0, (now - heartbeat).total_seconds())
            out.append(
                {
                    "id": agent_id,
                    "role": str(agent.get("role", "UNKNOWN")),
                    "state": str(agent.get("state", "UNKNOWN")),
                    "position": coerce_position(agent.get("position")),
                    "battery": clamp(coerce_float(agent.get("battery", 100.0), 100.0), 0.0, 100.0),
                    "capability": str(agent.get("capability", "general")),
                    "last_heartbeat": heartbeat.isoformat() if heartbeat else utc_now_iso(),
                    "time_since_heartbeat": round(delta, 2),
                    "mission_name": str(agent.get("mission_name", "None")),
                    "formation_position": formation_positions.get(agent_id, "unassigned"),
                }
            )
        return out

    def get_missions(self) -> List[Dict[str, Any]]:
        missions = [dict(item) for item in self._runtime.get("missions", []) if isinstance(item, dict)]
        out: List[Dict[str, Any]] = []
        for index, mission in enumerate(missions):
            out.append(
                {
                    "id": str(mission.get("id", f"mission-{index+1}")),
                    "type": str(mission.get("type", "unknown")),
                    "status": str(mission.get("status", "unknown")),
                    "assigned_agents": list(mission.get("assigned_agents", [])),
                    "progress_pct": clamp(coerce_float(mission.get("progress_pct", 0), 0), 0.0, 100.0),
                    "duration": coerce_float(mission.get("duration", 0), 0),
                    "waypoints_completed": coerce_int(mission.get("waypoints_completed", 0), 0),
                }
            )
        return out

    def get_swarm_status(self) -> Dict[str, Any]:
        roster = self.get_agent_roster()
        by_state: Dict[str, int] = {}
        for agent in roster:
            state = str(agent.get("state", "UNKNOWN")).upper()
            by_state[state] = by_state.get(state, 0) + 1
        formation = self.get_formation_data()
        return {
            "total_agents": len(roster),
            "by_state": by_state,
            "formation_type": formation.get("type", "UNKNOWN"),
            "formation_spacing": formation.get("spacing", 0),
            "last_command_issued": self._runtime.get("last_swarm_command"),
        }

    def get_decision_feed(self, limit: int = 20) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(coerce_int(limit, 20), 200))
        decisions = [dict(item) for item in self._runtime.get("decisions", []) if isinstance(item, dict)]
        out: List[Dict[str, Any]] = []
        for index, item in enumerate(reversed(decisions[-safe_limit:])):
            out.append(
                {
                    "id": str(item.get("id", f"decision-{index+1}")),
                    "type": str(item.get("type", "unknown")),
                    "agent_id": str(item.get("agent_id", "unknown")),
                    "confidence": clamp(coerce_float(item.get("confidence", 0.0), 0.0), 0.0, 1.0),
                    "risk_score": clamp(coerce_float(item.get("risk_score", 0.0), 0.0), 0.0, 1.0),
                    "requires_review": bool(item.get("requires_review", False)),
                    "reasoning_snippet": str(item.get("reasoning", item.get("summary", "No rationale provided.")))[:220],
                    "timestamp": str(item.get("timestamp", utc_now_iso())),
                    "status": str(item.get("status", "pending")),
                    "context": str(item.get("context", "")),
                }
            )
        return out

    def get_review_queue(self) -> List[Dict[str, Any]]:
        queue: List[Dict[str, Any]] = []
        for decision in self.get_decision_feed(limit=500):
            if not bool(decision.get("requires_review", False)):
                continue
            if str(decision.get("status", "")).lower() in {"approved", "rejected"}:
                continue
            row = deepcopy(decision)
            row["xai_explanation"] = self.get_decision_explanation(row["id"])
            queue.append(row)
        return queue

    def get_decision_explanation(self, decision_id: str) -> Dict[str, Any]:
        if not isinstance(decision_id, str) or not decision_id.strip():
            return {
                "decision_id": "",
                "summary": "invalid decision id",
                "factors": [],
                "alternatives": [],
                "risk_assessment": {},
            }
        if self._explainer is not None and hasattr(self._explainer, "explain_decision"):
            try:
                payload = self._explainer.explain_decision(decision_id)
                data = as_dict(payload)
                if data:
                    return data
            except Exception:
                pass
        for decision in self.get_decision_feed(limit=1000):
            if decision["id"] == decision_id:
                return {
                    "decision_id": decision_id,
                    "summary": decision.get("reasoning_snippet", ""),
                    "factors": decision.get("factors", []),
                    "alternatives": decision.get("alternatives", []),
                    "risk_assessment": {
                        "score": decision.get("risk_score", 0.0),
                        "requires_review": decision.get("requires_review", False),
                    },
                }
        return {
            "decision_id": decision_id,
            "summary": "Decision not found.",
            "factors": [],
            "alternatives": [],
            "risk_assessment": {"score": 0.0, "requires_review": False},
        }

    def get_formation_data(self) -> Dict[str, Any]:
        formation = self._runtime.get("formation", {})
        if not isinstance(formation, dict):
            formation = {}
        return {
            "type": str(formation.get("type", "UNKNOWN")),
            "positions": dict(formation.get("positions", {})),
            "formation_score": clamp(coerce_float(formation.get("score", 0.0), 0.0), 0.0, 1.0),
            "spacing": coerce_float(formation.get("spacing", 0.0), 0.0),
        }

    def send_nl_command(self, text: str, language: str = "en") -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            return {"status": "error", "detail": "text must be a non-empty string"}
        lang = str(language or "en").strip().lower()
        if lang not in {"en", "ar"}:
            lang = "en"
        lower = text.strip().lower()
        command = "unknown"
        if "hold" in lower or (lang == "ar" and any(token in text for token in ("ثبات", "تمركز", "انتظر"))):
            command = "hold_position"
        elif "return" in lower or "rtb" in lower:
            command = "return_to_base"
        elif "scan" in lower or "recon" in lower:
            command = "reconnaissance"
        parsed = {
            "command": command,
            "language": lang,
            "original_text": text.strip(),
            "confidence": 0.76,
            "args": {},
        }
        set_last_swarm_command(
            {
                "timestamp": utc_now_iso(),
                "language": lang,
                "text": text.strip(),
                "parsed": parsed,
            }
        )
        mark_updated()
        return {"status": "ok", "parsed_command": parsed}

    def apply_review_decision(self, decision_id: str, approved: bool, reason: Optional[str] = None) -> Dict[str, Any]:
        if not isinstance(decision_id, str) or not decision_id.strip():
            return {"status": "error", "detail": "decision_id must be a non-empty string"}
        decisions = [dict(item) for item in self._runtime.get("decisions", []) if isinstance(item, dict)]
        found = False
        for decision in decisions:
            if str(decision.get("id", "")) == decision_id:
                decision["status"] = "approved" if approved else "rejected"
                decision["reviewed_at"] = utc_now_iso()
                decision["review_reason"] = (reason or "").strip()
                decision["requires_review"] = False
                found = True
                break
        if not found:
            return {"status": "error", "detail": f"Decision not found: {decision_id}"}
        set_decisions(decisions)
        return {
            "status": "ok",
            "decision_id": decision_id,
            "review_status": "approved" if approved else "rejected",
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "active": self.active,
            "agents": len(self.get_agent_roster()),
            "missions": len(self.get_missions()),
            "review_queue": len(self.get_review_queue()),
        }
