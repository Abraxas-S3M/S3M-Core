"""Behavior tree nodes for tactical mission execution in contested environments.

The lightweight behavior tree runtime ensures autonomy logic remains available
even when optional BT frameworks are not installed on edge platforms.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Callable, Dict, List, Optional
import uuid

from src.autonomy.models import AutonomyDecision, DecisionType


class BTStatus(Enum):
    """Node execution status for behavior tree ticking."""

    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


class BTNode(ABC):
    """Abstract behavior tree node used for tactical mission logic."""

    def __init__(self, name: str, children: Optional[List["BTNode"]] = None) -> None:
        self.name = name
        self.children: List["BTNode"] = children or []
        self.parent: Optional["BTNode"] = None
        self.last_status: Optional[BTStatus] = None
        for child in self.children:
            child.parent = self

    @abstractmethod
    def tick(self, context: Dict[str, Any]) -> BTStatus:
        """Execute one node tick and return current status."""

    def reset(self) -> None:
        """Reset node state recursively for mission re-execution."""
        self.last_status = None
        for child in self.children:
            child.reset()

    def active_path(self) -> List[str]:
        """Return recently active path for tactical debugging/XAI tooling."""
        path = [self.name]
        for child in self.children:
            if child.last_status in {BTStatus.RUNNING, BTStatus.SUCCESS}:
                path.extend(child.active_path())
                break
        return path

    def get_active_path(self) -> List[str]:
        """Compatibility alias used by mission executor/XAI tooling."""
        return self.active_path()

    def _log_decision(
        self,
        context: Dict[str, Any],
        decision_type: DecisionType,
        action_taken: Dict[str, Any],
        reasoning: str,
        confidence: float = 0.7,
        risk_score: float = 0.4,
        llm_consulted: bool = False,
        alternatives_considered: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Append an auditable decision record for each tactical node action."""
        decision_log = context.setdefault("decision_log", [])
        mission_id = context.get("mission_id")
        agent_id = str(context.get("agent_id", "unknown_agent"))
        decision = AutonomyDecision(
            decision_id=f"dec-{uuid.uuid4().hex[:10]}",
            timestamp=datetime.now(timezone.utc),
            decision_type=decision_type,
            agent_id=agent_id,
            mission_id=mission_id,
            context=dict(context),
            action_taken=action_taken,
            alternatives_considered=alternatives_considered or [],
            confidence=max(0.0, min(1.0, confidence)),
            reasoning=reasoning,
            llm_consulted=llm_consulted,
            requires_human_review=False,
            risk_score=max(0.0, min(1.0, risk_score)),
        )
        decision_log.append(decision)


class SequenceNode(BTNode):
    """Execute children in order until one fails or all succeed."""

    def __init__(self, name: str, children: Optional[List[BTNode]] = None) -> None:
        super().__init__(name, children)
        self._current_index = 0

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        while self._current_index < len(self.children):
            status = self.children[self._current_index].tick(context)
            self.last_status = status
            if status == BTStatus.RUNNING:
                return BTStatus.RUNNING
            if status == BTStatus.FAILURE:
                self._current_index = 0
                return BTStatus.FAILURE
            self._current_index += 1
        self._current_index = 0
        self.last_status = BTStatus.SUCCESS
        return BTStatus.SUCCESS

    def reset(self) -> None:
        super().reset()
        self._current_index = 0


class SelectorNode(BTNode):
    """Execute children in order until one succeeds."""

    def __init__(self, name: str, children: Optional[List[BTNode]] = None) -> None:
        super().__init__(name, children)
        self._current_index = 0

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        while self._current_index < len(self.children):
            status = self.children[self._current_index].tick(context)
            self.last_status = status
            if status == BTStatus.RUNNING:
                return BTStatus.RUNNING
            if status == BTStatus.SUCCESS:
                self._current_index = 0
                return BTStatus.SUCCESS
            self._current_index += 1
        self._current_index = 0
        self.last_status = BTStatus.FAILURE
        return BTStatus.FAILURE

    def reset(self) -> None:
        super().reset()
        self._current_index = 0


class ConditionNode(BTNode):
    """Condition wrapper that evaluates tactical state constraints."""

    def __init__(self, name: str, check_fn: Callable[[Dict[str, Any]], bool]) -> None:
        super().__init__(name, [])
        self.check_fn = check_fn

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        try:
            status = BTStatus.SUCCESS if bool(self.check_fn(context)) else BTStatus.FAILURE
        except Exception:
            status = BTStatus.FAILURE
        self.last_status = status
        return status


class ActionNode(BTNode):
    """Action wrapper for tactical behavior function callbacks."""

    def __init__(self, name: str, action_fn: Callable[[Dict[str, Any]], BTStatus]) -> None:
        super().__init__(name, [])
        self.action_fn = action_fn

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        try:
            status = self.action_fn(context)
        except Exception:
            status = BTStatus.FAILURE
        self.last_status = status
        return status


class RepeatNode(BTNode):
    """Repeat child execution a fixed number of times or until failure."""

    def __init__(self, name: str, child: BTNode, count: int = 1) -> None:
        super().__init__(name, [child])
        self.count = max(1, int(count))
        self._iterations = 0

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        child = self.children[0]
        status = child.tick(context)
        if status == BTStatus.FAILURE:
            self._iterations = 0
            self.last_status = BTStatus.FAILURE
            return BTStatus.FAILURE
        if status == BTStatus.RUNNING:
            self.last_status = BTStatus.RUNNING
            return BTStatus.RUNNING
        self._iterations += 1
        if self._iterations >= self.count:
            self._iterations = 0
            self.last_status = BTStatus.SUCCESS
            return BTStatus.SUCCESS
        self.last_status = BTStatus.RUNNING
        return BTStatus.RUNNING

    def reset(self) -> None:
        super().reset()
        self._iterations = 0


class InverterNode(BTNode):
    """Invert SUCCESS/FAILURE status for tactical fallback logic."""

    def __init__(self, name: str, child: BTNode) -> None:
        super().__init__(name, [child])

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        status = self.children[0].tick(context)
        if status == BTStatus.SUCCESS:
            self.last_status = BTStatus.FAILURE
            return BTStatus.FAILURE
        if status == BTStatus.FAILURE:
            self.last_status = BTStatus.SUCCESS
            return BTStatus.SUCCESS
        self.last_status = BTStatus.RUNNING
        return BTStatus.RUNNING


def _distance(a: List[float] | tuple, b: List[float] | tuple) -> float:
    return float(math.dist((a[0], a[1], a[2]), (b[0], b[1], b[2])))


class PatrolNode(BTNode):
    """Patrol waypoints to maintain presence in a tactical sector."""

    def __init__(self, name: str = "patrol") -> None:
        super().__init__(name, [])

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        waypoints = context.get("waypoints", [])
        if not waypoints:
            self._log_decision(
                context,
                DecisionType.HOLD,
                {"node": self.name, "action": "no_waypoints"},
                "No patrol waypoints available, holding position.",
                confidence=0.6,
                risk_score=0.2,
            )
            self.last_status = BTStatus.FAILURE
            return BTStatus.FAILURE

        idx = int(context.get("current_waypoint_idx", 0))
        idx = max(0, min(idx, len(waypoints) - 1))
        pos = list(context.get("agent_position", (0.0, 0.0, 0.0)))
        waypoint = waypoints[idx]
        move_step = float(context.get("patrol_step", 5.0))

        dx = waypoint[0] - pos[0]
        dy = waypoint[1] - pos[1]
        dz = waypoint[2] - pos[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist <= move_step:
            context["agent_position"] = tuple(waypoint)
            next_idx = idx + 1
            if next_idx >= len(waypoints):
                if bool(context.get("patrol_loop", False)):
                    context["current_waypoint_idx"] = 0
                    self.last_status = BTStatus.RUNNING
                else:
                    context["current_waypoint_idx"] = len(waypoints) - 1
                    self.last_status = BTStatus.SUCCESS
            else:
                context["current_waypoint_idx"] = next_idx
                self.last_status = BTStatus.RUNNING
        else:
            scale = move_step / max(dist, 1e-6)
            context["agent_position"] = (
                pos[0] + dx * scale,
                pos[1] + dy * scale,
                pos[2] + dz * scale,
            )
            self.last_status = BTStatus.RUNNING

        self._log_decision(
            context,
            DecisionType.HOLD,
            {"node": self.name, "target_waypoint": waypoint, "waypoint_index": idx},
            "Patrol maneuver executed to sustain sector coverage and early warning.",
            confidence=0.8,
            risk_score=0.3,
        )
        return self.last_status


class EngageNode(BTNode):
    """Engage the nearest threat when ROE permits tactical action."""

    def __init__(self, name: str = "engage") -> None:
        super().__init__(name, [])

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        roe = str(context.get("rules_of_engagement", "weapons_hold"))
        threats = context.get("threats", [])
        pos = context.get("agent_position", (0.0, 0.0, 0.0))
        range_m = float(context.get("engagement_range", 30.0))

        if roe == "weapons_hold":
            self._log_decision(
                context,
                DecisionType.HOLD,
                {"node": self.name, "action": "engagement_blocked"},
                "Engagement denied by weapons_hold rules of engagement.",
                confidence=0.95,
                risk_score=0.1,
            )
            self.last_status = BTStatus.FAILURE
            return BTStatus.FAILURE

        if not threats:
            self._log_decision(
                context,
                DecisionType.HOLD,
                {"node": self.name, "action": "no_targets"},
                "No valid threat target available for engagement.",
                confidence=0.7,
                risk_score=0.2,
            )
            self.last_status = BTStatus.FAILURE
            return BTStatus.FAILURE

        nearest_idx = None
        nearest_dist = float("inf")
        for idx, threat in enumerate(threats):
            t_pos = threat.get("position", (0.0, 0.0, 0.0))
            dist = _distance(pos, t_pos)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = idx

        if nearest_idx is None or nearest_dist > range_m:
            self._log_decision(
                context,
                DecisionType.HOLD,
                {"node": self.name, "action": "target_out_of_range", "distance": nearest_dist},
                "Nearest threat outside engagement envelope; holding fire.",
                confidence=0.75,
                risk_score=0.4,
            )
            self.last_status = BTStatus.FAILURE
            return BTStatus.FAILURE

        threat = threats.pop(nearest_idx)
        context["threats"] = threats
        self._log_decision(
            context,
            DecisionType.ENGAGE,
            {"node": self.name, "neutralized_target": threat, "distance": nearest_dist},
            "Threat engaged and neutralized to protect mission force package.",
            confidence=0.88,
            risk_score=0.65,
        )
        self.last_status = BTStatus.SUCCESS
        return BTStatus.SUCCESS


class ReconNode(BTNode):
    """Observe designated recon area to gather tactical intelligence."""

    def __init__(self, name: str = "recon") -> None:
        super().__init__(name, [])

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        area = context.get("recon_area")
        if not area:
            self.last_status = BTStatus.FAILURE
            return BTStatus.FAILURE
        duration = int(context.get("observation_duration", 5))
        observed = int(context.get("observed_ticks", 0))
        observed += 1
        context["observed_ticks"] = observed
        context.setdefault("recon_observations", []).append(
            {"tick": observed, "area": area, "note": "Sector scanned for hostile movement."}
        )
        self._log_decision(
            context,
            DecisionType.HOLD,
            {"node": self.name, "observation_tick": observed, "recon_area": area},
            "Recon observation cycle executed to improve situational awareness.",
            confidence=0.82,
            risk_score=0.25,
        )
        if observed >= duration:
            self.last_status = BTStatus.SUCCESS
            return BTStatus.SUCCESS
        self.last_status = BTStatus.RUNNING
        return BTStatus.RUNNING


class RetreatNode(BTNode):
    """Retreat from threat axis toward safe zone to preserve combat power."""

    def __init__(self, name: str = "retreat") -> None:
        super().__init__(name, [])

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        safe_zone = context.get("safe_zone", (0.0, 0.0, 0.0))
        pos = list(context.get("agent_position", (0.0, 0.0, 0.0)))
        threats = context.get("threats", [])
        step = float(context.get("retreat_step", 8.0))

        if threats:
            nearest = min(threats, key=lambda t: _distance(pos, t.get("position", (0.0, 0.0, 0.0))))
            t_pos = nearest.get("position", (0.0, 0.0, 0.0))
            dx = pos[0] - t_pos[0]
            dy = pos[1] - t_pos[1]
            dz = pos[2] - t_pos[2]
        else:
            dx = safe_zone[0] - pos[0]
            dy = safe_zone[1] - pos[1]
            dz = safe_zone[2] - pos[2]

        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 1e-6:
            context["agent_position"] = tuple(pos)
        else:
            scale = step / max(length, 1e-6)
            context["agent_position"] = (
                pos[0] + dx * scale,
                pos[1] + dy * scale,
                pos[2] + dz * scale,
            )

        safe_distance = float(context.get("safe_distance", 80.0))
        nearest_dist = float("inf")
        if threats:
            nearest_dist = min(_distance(context["agent_position"], t.get("position", (0.0, 0.0, 0.0))) for t in threats)
        if nearest_dist >= safe_distance:
            self.last_status = BTStatus.SUCCESS
        else:
            self.last_status = BTStatus.RUNNING

        self._log_decision(
            context,
            DecisionType.RETREAT,
            {"node": self.name, "safe_zone": safe_zone, "nearest_threat_distance": nearest_dist},
            "Retreat maneuver prioritized force survival under elevated threat pressure.",
            confidence=0.9,
            risk_score=0.45,
        )
        return self.last_status


class HoldNode(BTNode):
    """Hold tactical position while awaiting updated command authority."""

    def __init__(self, name: str = "hold") -> None:
        super().__init__(name, [])

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        hold_ticks = int(context.get("hold_ticks", 0)) + 1
        context["hold_ticks"] = hold_ticks
        context.setdefault("hold_log", []).append(
            {"tick": hold_ticks, "position": context.get("agent_position", (0.0, 0.0, 0.0))}
        )
        self._log_decision(
            context,
            DecisionType.HOLD,
            {"node": self.name, "hold_ticks": hold_ticks},
            "Holding position to maintain tactical stability and sensor coverage.",
            confidence=0.85,
            risk_score=0.2,
        )
        self.last_status = BTStatus.RUNNING
        return BTStatus.RUNNING


class RTBNode(BTNode):
    """Return to base to recover platform before combat effectiveness degrades."""

    def __init__(self, name: str = "rtb") -> None:
        super().__init__(name, [])

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        base = context.get("base_position", (0.0, 0.0, 0.0))
        pos = list(context.get("agent_position", (0.0, 0.0, 0.0)))
        step = float(context.get("rtb_step", 10.0))
        dx = base[0] - pos[0]
        dy = base[1] - pos[1]
        dz = base[2] - pos[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist <= step:
            context["agent_position"] = tuple(base)
            self.last_status = BTStatus.SUCCESS
        else:
            scale = step / max(dist, 1e-6)
            context["agent_position"] = (
                pos[0] + dx * scale,
                pos[1] + dy * scale,
                pos[2] + dz * scale,
            )
            self.last_status = BTStatus.RUNNING
        self._log_decision(
            context,
            DecisionType.DELEGATE,
            {"node": self.name, "base_position": base, "distance_to_base": dist},
            "Return-to-base maneuver initiated to preserve platform readiness.",
            confidence=0.9,
            risk_score=0.15,
        )
        return self.last_status
