"""Behavior tree node that consults the S3M LLM for tactical replanning.

When static behavior logic is insufficient, this node escalates to Layer 01
LLM reasoning to obtain mission-safe guidance while preserving auditability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
import uuid

from src.autonomy.models import AutonomyDecision, CommandType, DecisionType
from .nodes import BTNode, BTStatus


class LLMReplanNode(BTNode):
    """Invoke LLM orchestrator for tactical guidance during uncertainty."""

    def __init__(self, name: str = "llm_replan", domain: str = "tactical"):
        super().__init__(name=name)
        self.domain = domain
        self.last_prompt = ""
        self.last_response = ""

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        failed = context.get("last_failed_node", "unknown")
        agent_state = context.get("agent_state", {})
        mission = context.get("mission", {})
        threats = context.get("threats", [])
        return (
            "S3M Tactical Replan Request\n"
            f"Domain: {self.domain}\n"
            f"Failed behavior: {failed}\n"
            f"Agent state: {agent_state}\n"
            f"Mission status: {mission}\n"
            f"Nearby threats: {threats}\n"
            "Respond with one keyword action: ENGAGE, RETREAT, HOLD, REROUTE, ESCALATE. "
            "Include a one-sentence tactical rationale."
        )

    def _parse_action(self, text: str) -> CommandType | None:
        upper = (text or "").upper()
        if "ENGAGE" in upper:
            return CommandType.ENGAGE
        if "RETREAT" in upper:
            return CommandType.DISENGAGE
        if "HOLD" in upper:
            return CommandType.HOLD
        if "REROUTE" in upper:
            return CommandType.REPLAN
        if "ESCALATE" in upper:
            return CommandType.REPLAN
        return None

    def tick(self, context: Dict[str, Any]) -> BTStatus:
        decision_log = context.setdefault("decision_log", [])
        prompt = self._build_prompt(context)
        self.last_prompt = prompt
        try:
            from src.llm_core.orchestrator import Orchestrator, QueryRequest

            orchestrator = Orchestrator()
            request = QueryRequest(prompt=prompt, domain=self.domain)
            response = orchestrator.process(request)
            text = getattr(response, "text", "") or getattr(response, "final_answer", "")
            self.last_response = text
            action = self._parse_action(text)
            if action is None:
                context["replan_reason"] = "LLM response unparseable"
                decision = AutonomyDecision(
                    decision_id=f"dec-{uuid.uuid4().hex[:12]}",
                    timestamp=datetime.now(timezone.utc),
                    decision_type=DecisionType.REPLAN,
                    agent_id=str(context.get("agent_id", "unknown")),
                    mission_id=context.get("mission_id"),
                    context={"prompt": prompt},
                    action_taken={"result": "no_action"},
                    alternatives_considered=[],
                    confidence=0.35,
                    reasoning="LLM response did not contain recognized tactical action keywords.",
                    llm_consulted=True,
                    requires_human_review=False,
                    risk_score=0.3,
                )
                decision_log.append(decision)
                return BTStatus.FAILURE

            context["replan_command"] = {
                "command_type": action.value,
                "source": "llm_replan",
                "raw_response": text,
            }
            decision = AutonomyDecision(
                decision_id=f"dec-{uuid.uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc),
                decision_type=DecisionType.REPLAN,
                agent_id=str(context.get("agent_id", "unknown")),
                mission_id=context.get("mission_id"),
                context={"prompt": prompt},
                action_taken={
                    "command_type": action.value,
                    "raw_response": text,
                },
                alternatives_considered=[
                    {"action": "HOLD", "reason_rejected": "LLM advised alternative tactical maneuver"}
                ],
                confidence=0.6,
                reasoning=f"LLM recommended {action.value} based on current threat/mission context.",
                llm_consulted=True,
                requires_human_review=action == CommandType.ENGAGE,
                risk_score=0.55 if action == CommandType.ENGAGE else 0.35,
            )
            decision_log.append(decision)
            return BTStatus.SUCCESS
        except Exception:
            context["replan_reason"] = "LLM unavailable — defaulting to current mission"
            decision = AutonomyDecision(
                decision_id=f"dec-{uuid.uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc),
                decision_type=DecisionType.REPLAN,
                agent_id=str(context.get("agent_id", "unknown")),
                mission_id=context.get("mission_id"),
                context={"prompt": prompt},
                action_taken={"result": "fallback_no_llm"},
                alternatives_considered=[],
                confidence=0.2,
                reasoning="LLM unavailable, retained current mission branch.",
                llm_consulted=True,
                requires_human_review=False,
                risk_score=0.2,
            )
            decision_log.append(decision)
            return BTStatus.FAILURE
