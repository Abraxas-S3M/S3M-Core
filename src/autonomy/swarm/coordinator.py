"""Central swarm coordinator for Layer 03 autonomous multi-agent control.

Coordinates agent registration, mission assignment, command issuance, and
formation management under tactical command-and-control constraints.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import copy
import uuid

from src.autonomy.models import (
    AgentCapability,
    AgentInfo,
    AgentRole,
    AgentState,
    CommandType,
    FormationType,
    Mission,
    MissionStatus,
    SwarmCommand,
)

from .formations import FormationController
from .swarm_protocol import SwarmProtocol
from .task_allocator import TaskAllocator


class SwarmCoordinator:
    """Control-plane class for tactical swarm operations and mission management."""

    def __init__(self, max_agents: int = 50) -> None:
        if max_agents <= 0:
            raise ValueError("max_agents must be > 0")
        self.max_agents = int(max_agents)
        self.agents: Dict[str, AgentInfo] = {}
        self.missions: Dict[str, Mission] = {}
        self.mission_assignments: Dict[str, Dict[str, str]] = {}
        self.command_queue: List[SwarmCommand] = []
        self.command_history: List[SwarmCommand] = []
        self.max_command_history = 1000
        self.max_missions = 100

        self.formation_controller = FormationController()
        self.task_allocator = TaskAllocator()
        self.protocol = SwarmProtocol()

        self.current_formation: Optional[Dict[str, Any]] = None
        self.last_command: Optional[SwarmCommand] = None
        self.audit_log: List[Dict[str, Any]] = []

    def _log(self, action: str, details: Dict[str, Any]) -> None:
        self.audit_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "details": copy.deepcopy(details),
            }
        )
        if len(self.audit_log) > 5000:
            self.audit_log = self.audit_log[-5000:]

    def register_agent(self, agent_info: AgentInfo) -> None:
        """Register an agent into the swarm roster."""
        if len(self.agents) >= self.max_agents and agent_info.agent_id not in self.agents:
            raise ValueError("max_agents limit reached")
        self.agents[agent_info.agent_id] = agent_info
        self._log("register_agent", {"agent_id": agent_info.agent_id})

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent from the swarm roster."""
        self.agents.pop(agent_id, None)
        self._log("remove_agent", {"agent_id": agent_id})

    def update_agent(self, agent_id: str, **kwargs: Any) -> None:
        """Update mutable fields on an existing agent state record."""
        agent = self.agents.get(agent_id)
        if agent is None:
            raise KeyError(f"unknown agent_id: {agent_id}")

        allowed = {
            "role",
            "state",
            "capability",
            "position",
            "heading",
            "speed",
            "battery_pct",
            "fuel_pct",
            "current_mission",
            "last_heartbeat",
            "sensor_loadout",
            "weapon_loadout",
            "comms_status",
        }
        updates: Dict[str, Any] = {}
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "role" and isinstance(value, str):
                value = AgentRole(value)
            if key == "state" and isinstance(value, str):
                value = AgentState(value)
            if key == "capability" and isinstance(value, str):
                value = AgentCapability(value)
            if key == "position":
                if not isinstance(value, (tuple, list)) or len(value) != 3:
                    raise ValueError("position must be a 3D tuple/list")
                value = (float(value[0]), float(value[1]), float(value[2]))
            setattr(agent, key, value)
            updates[key] = value.value if hasattr(value, "value") else value
        if updates:
            self._log("update_agent", {"agent_id": agent_id, "updates": updates})

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """Fetch a single agent by ID."""
        return self.agents.get(agent_id)

    def get_agents(
        self,
        state: Optional[AgentState | str] = None,
        role: Optional[AgentRole | str] = None,
        capability: Optional[AgentCapability | str] = None,
    ) -> List[AgentInfo]:
        """Filter agents by state, role, and capability criteria."""
        state_val = state.value if isinstance(state, AgentState) else state
        role_val = role.value if isinstance(role, AgentRole) else role
        cap_val = capability.value if isinstance(capability, AgentCapability) else capability
        output: List[AgentInfo] = []
        for agent in self.agents.values():
            if state_val and agent.state.value != state_val:
                continue
            if role_val and agent.role.value != role_val:
                continue
            if cap_val and agent.capability.value != cap_val:
                continue
            output.append(agent)
        return output

    def assign_mission(self, mission: Mission) -> Dict[str, str]:
        """Assign mission roles using allocator and update agent mission links."""
        if len(self.missions) >= self.max_missions and mission.mission_id not in self.missions:
            raise ValueError("mission registry full")
        available = list(self.agents.values())
        assignments = self.task_allocator.allocate(mission, available)
        mission.assigned_agents = list(assignments.keys())
        self.missions[mission.mission_id] = mission
        self.mission_assignments[mission.mission_id] = dict(assignments)
        for agent_id in assignments:
            if agent_id in self.agents:
                self.agents[agent_id].current_mission = mission.mission_id
        self._log(
            "assign_mission",
            {"mission_id": mission.mission_id, "assignments": assignments, "status": mission.status.value},
        )
        return assignments

    def start_mission(self, mission_id: str) -> bool:
        """Transition mission to active state if present and assignable."""
        mission = self.missions.get(mission_id)
        if mission is None:
            return False
        mission.status = MissionStatus.ACTIVE
        mission.started_at = datetime.now(timezone.utc)
        for agent_id in mission.assigned_agents:
            if agent_id in self.agents:
                self.agents[agent_id].state = AgentState.EXECUTING
        self._log("start_mission", {"mission_id": mission_id})
        return True

    def abort_mission(self, mission_id: str) -> None:
        """Abort active mission and release assigned agents."""
        mission = self.missions.get(mission_id)
        if mission is None:
            return
        mission.status = MissionStatus.ABORTED
        mission.completed_at = datetime.now(timezone.utc)
        for agent_id in mission.assigned_agents:
            if agent_id in self.agents:
                self.agents[agent_id].state = AgentState.RETURNING
                self.agents[agent_id].current_mission = None
        self._log("abort_mission", {"mission_id": mission_id})

    def get_mission(self, mission_id: str) -> Optional[Mission]:
        """Get mission by identifier."""
        return self.missions.get(mission_id)

    def get_active_missions(self) -> List[Mission]:
        """List missions currently active in tactical execution."""
        return [m for m in self.missions.values() if m.status == MissionStatus.ACTIVE]

    def issue_command(self, command: SwarmCommand) -> bool:
        """Validate and queue command for swarm execution."""
        valid, reason = self.protocol.validate_command(command)
        if not valid:
            self._log("reject_command", {"command_id": command.command_id, "reason": reason})
            return False
        self.command_queue.append(command)
        self.command_history.append(command)
        if len(self.command_history) > self.max_command_history:
            self.command_history = self.command_history[-self.max_command_history :]
        self.last_command = command
        self._log("issue_command", {"command_id": command.command_id, "type": command.command_type.value})
        return True

    def set_formation(self, formation_type: FormationType, spacing: float = 20.0) -> SwarmCommand:
        """Create and queue formation change command based on active roster."""
        if not self.agents:
            raise ValueError("no agents registered")
        leader = sorted(self.agents.values(), key=lambda a: a.agent_id)[0]
        positions = self.formation_controller.compute_formation(
            formation_type=formation_type,
            leader_position=leader.position,
            heading=leader.heading,
            n_agents=len(self.agents),
            spacing=spacing,
        )
        id_order = [leader.agent_id] + [aid for aid in self.agents if aid != leader.agent_id]
        target_positions = {
            id_order[idx]: pos for idx, pos in positions.items() if idx < len(id_order)
        }
        self.current_formation = {
            "formation_type": formation_type.value,
            "spacing": spacing,
            "target_positions": target_positions,
        }
        cmd = self.protocol.create_command(
            command_type=CommandType.CHANGE_FORMATION,
            target_agents=["all"],
            parameters={
                "formation_type": formation_type.value,
                "spacing": spacing,
                "target_positions": target_positions,
            },
            issued_by="autonomy",
            priority=2,
            ttl=60.0,
        )
        self.issue_command(cmd)
        return cmd

    def emergency_stop(self) -> SwarmCommand:
        """Issue immediate high-priority stop command for all agents."""
        cmd = self.protocol.create_emergency_stop()
        self.issue_command(cmd)
        return cmd

    def get_command_history(self, limit: int = 50) -> List[SwarmCommand]:
        """Return most recent command entries, newest last."""
        lim = max(1, int(limit))
        return self.command_history[-lim:]

    def get_swarm_status(self) -> Dict[str, Any]:
        """Summarize swarm posture for tactical dashboard reporting."""
        states = Counter(agent.state.value for agent in self.agents.values())
        roles = Counter(agent.role.value for agent in self.agents.values())
        return {
            "total_agents": len(self.agents),
            "by_state": dict(states),
            "by_role": dict(roles),
            "active_missions": [m.mission_id for m in self.get_active_missions()],
            "current_formation": copy.deepcopy(self.current_formation),
            "last_command": self.last_command.to_dict() if self.last_command else None,
            "queued_commands": len(self.command_queue),
        }

    def health_check(self) -> Dict[str, Any]:
        """Return health snapshot for autonomy subsystem monitoring."""
        expired = len([c for c in self.command_queue if c.is_expired()])
        return {
            "status": "operational",
            "max_agents": self.max_agents,
            "registered_agents": len(self.agents),
            "missions_registered": len(self.missions),
            "active_missions": len(self.get_active_missions()),
            "command_queue_depth": len(self.command_queue),
            "expired_commands": expired,
            "allocator_log_entries": len(self.task_allocator.allocation_log),
        }
