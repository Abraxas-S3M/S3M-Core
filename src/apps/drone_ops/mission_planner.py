"""Mission planning orchestration for drone operations domain app."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from src.apps._shared import ensure_non_empty_text, normalize_coords, safe_int, utc_now_iso
from src.llm_core import Orchestrator, QueryRequest, TaskDomain


class MissionPlanner:
    """Create mission plans by wiring autonomy/navigation layer components when available."""

    def __init__(self) -> None:
        self.orchestrator = Orchestrator()
        self._missions: Dict[str, dict] = {}
        self._swarm_coordinator = self._maybe_create_swarm_coordinator()
        self._task_allocator = self._maybe_create_task_allocator()
        self._trajectory_optimizer = self._maybe_create_trajectory_optimizer()

    def _maybe_create_swarm_coordinator(self) -> Any | None:
        try:
            from src.autonomy.swarm_coordinator import SwarmCoordinator

            return SwarmCoordinator()
        except Exception:
            return None

    def _maybe_create_task_allocator(self) -> Any | None:
        try:
            from src.autonomy.task_allocator import TaskAllocator

            return TaskAllocator()
        except Exception:
            return None

    def _maybe_create_trajectory_optimizer(self) -> Any | None:
        try:
            from src.navigation.trajectory_optimizer import TrajectoryOptimizer

            return TrajectoryOptimizer()
        except Exception:
            return None

    def _validate_request(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise ValueError("request must be a dictionary")
        mission_type = ensure_non_empty_text(request.get("mission_type", "PATROL"), "mission_type").upper()
        waypoints_raw = request.get("waypoints", [])
        if not isinstance(waypoints_raw, list) or not waypoints_raw:
            raise ValueError("waypoints must be a non-empty list")
        waypoints = [normalize_coords(item, dims=3) for item in waypoints_raw]
        return {
            "mission_type": mission_type,
            "waypoints": waypoints,
            "platform_type": str(request.get("platform_type", "quadrotor")),
            "rules_of_engagement": str(request.get("rules_of_engagement", "weapons_tight")),
            "num_agents": max(1, safe_int(request.get("num_agents", 1), 1)),
            "description": str(request.get("description", "")),
        }

    def _pick_bt_template(self, mission_type: str) -> str:
        mapping = {
            "PATROL": "patrol.yaml",
            "RECON": "recon.yaml",
            "INTERCEPT": "intercept.yaml",
        }
        return mapping.get(mission_type, "patrol.yaml")

    def _assign_agents(self, num_agents: int) -> Dict[str, str]:
        registered_agents: List[str] = []
        if self._swarm_coordinator is not None:
            try:
                agents = getattr(self._swarm_coordinator, "get_agents", lambda: [])()
                for entry in agents or []:
                    if isinstance(entry, dict) and entry.get("agent_id"):
                        registered_agents.append(str(entry["agent_id"]))
                    elif isinstance(entry, str):
                        registered_agents.append(entry)
            except Exception:
                registered_agents = []
        if len(registered_agents) < num_agents:
            registered_agents.extend([f"agent-{idx + 1}" for idx in range(len(registered_agents), num_agents)])
        selected = registered_agents[:num_agents]

        if self._task_allocator is not None:
            try:
                assignments = self._task_allocator.allocate(
                    agents=[{"agent_id": agent_id} for agent_id in selected],
                    tasks=[{"task_id": f"task-{idx}", "role": "mission"} for idx in range(num_agents)],
                )
                parsed: Dict[str, str] = {}
                for entry in assignments or []:
                    if isinstance(entry, dict):
                        parsed[str(entry.get("agent_id", ""))] = str(entry.get("role", "mission"))
                if parsed:
                    return parsed
            except Exception:
                pass

        roles = ["lead", "wing", "relay", "reserve"]
        return {agent_id: roles[idx] if idx < len(roles) else "support" for idx, agent_id in enumerate(selected)}

    def _optimize_trajectory(self, points: List[tuple], platform_type: str) -> dict:
        if self._trajectory_optimizer is not None:
            try:
                out = self._trajectory_optimizer.optimize(points, platform_type=platform_type)
                if isinstance(out, dict):
                    return out
            except Exception:
                pass
        dist = 0.0
        for idx in range(1, len(points)):
            ax, ay, az = points[idx - 1]
            bx, by, bz = points[idx]
            dist += ((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2) ** 0.5
        return {"path": points, "distance_m": dist, "estimated_time_s": dist / 12.0 if dist else 0.0}

    def plan_mission(self, request: dict) -> dict:
        payload = self._validate_request(request)
        mission_id = f"mission-{uuid.uuid4().hex[:12]}"
        agents_assigned = self._assign_agents(payload["num_agents"])
        trajectories: Dict[str, dict] = {}
        for agent_id in agents_assigned:
            trajectories[agent_id] = self._optimize_trajectory(payload["waypoints"], payload["platform_type"])
        estimated = max((safe_int(val.get("estimated_time_s", 0)) for val in trajectories.values()), default=0)
        plan = {
            "mission_id": mission_id,
            "mission_type": payload["mission_type"],
            "agents_assigned": agents_assigned,
            "waypoints": payload["waypoints"],
            "trajectories": trajectories,
            "behavior_tree": self._pick_bt_template(payload["mission_type"]),
            "estimated_duration_s": float(estimated),
            "status": "planned",
            "rules_of_engagement": payload["rules_of_engagement"],
            "platform_type": payload["platform_type"],
            "description": payload["description"],
            "timestamp": utc_now_iso(),
        }
        self._missions[mission_id] = plan
        return plan

    def _extract_plan_from_text(self, text: str, language: str = "en") -> dict:
        if language == "ar":
            prompt = (
                "استخرج JSON فقط يتضمن: mission_type, waypoints, num_agents, rules_of_engagement من النص التالي: "
                f"{text}"
            )
            domain = TaskDomain.ARABIC_NLP
        else:
            prompt = (
                "Extract JSON only with mission_type, waypoints, num_agents, rules_of_engagement "
                f"from this mission request: {text}"
            )
            domain = TaskDomain.TACTICAL
        try:
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=domain))
            data = json.loads(getattr(response, "text", "{}"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {
            "mission_type": "RECON" if "recon" in text.lower() else "PATROL",
            "waypoints": [(0.0, 0.0, 40.0), (500.0, 300.0, 60.0)],
            "num_agents": 2 if "two" in text.lower() else 1,
            "rules_of_engagement": "weapons_tight",
            "description": text,
        }

    def plan_from_nl(self, natural_language: str, language: str = "en") -> dict:
        text = ensure_non_empty_text(natural_language, "natural_language")
        parsed = self._extract_plan_from_text(text, language=language)
        parsed.setdefault("description", text)
        return self.plan_mission(parsed)

    def execute(self, mission_id: str) -> dict:
        if mission_id not in self._missions:
            raise ValueError(f"unknown mission_id: {mission_id}")
        self._missions[mission_id]["status"] = "executing"
        self._missions[mission_id]["started_at"] = utc_now_iso()
        return {"mission_id": mission_id, "status": "executing"}

    def get_missions(self) -> List[dict]:
        return list(self._missions.values())

    def abort_mission(self, mission_id: str) -> dict:
        if mission_id not in self._missions:
            raise ValueError(f"unknown mission_id: {mission_id}")
        self._missions[mission_id]["status"] = "aborted"
        self._missions[mission_id]["aborted_at"] = utc_now_iso()
        return {"mission_id": mission_id, "status": "aborted"}
