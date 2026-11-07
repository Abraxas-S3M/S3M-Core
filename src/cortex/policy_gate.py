"""Cortex PolicyGate for fail-closed agent action authority.

Military/tactical context:
Cyber-defence agents operate in contested spaces where compromised autonomy
must not expand scope. This gate enforces commander envelopes and out-of-band
human approvals before any state-mutating tool invocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


_GIT_WRITE_SUBCOMMANDS = frozenset(
    {
        "add",
        "am",
        "checkout",
        "cherry-pick",
        "clean",
        "commit",
        "merge",
        "mv",
        "pull",
        "push",
        "rebase",
        "reset",
        "revert",
        "rm",
        "stash",
        "tag",
    }
)
_XIID_MUTATING_CLASSES = frozenset({"C", "D"})


@dataclass(frozen=True, slots=True)
class MissionEnvelope:
    """Commander-approved mission bounds carried with mutating tool requests."""

    envelope_id: str
    mission_id: str
    approved_by: str
    scope: str = "cyber_defence"
    constraints: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str]:
        if not str(self.envelope_id).strip():
            return False, "envelope_id is required"
        if not str(self.mission_id).strip():
            return False, "mission_id is required"
        if not str(self.approved_by).strip():
            return False, "approved_by is required"
        return True, "envelope valid"


@dataclass(frozen=True, slots=True)
class Approval:
    """Out-of-band human approval bound to a proposed agent action."""

    approver: str
    proposer: str
    channel: str
    approved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_valid(self) -> bool:
        if not str(self.approver).strip() or not str(self.proposer).strip():
            return False
        if self.approver == self.proposer:
            return False
        return str(self.channel).strip() == "out_of_band_device"


@dataclass(frozen=True, slots=True)
class PolicyVerdict:
    """Normalized policy decision returned to the orchestrator."""

    allowed: bool
    reason: str


class PolicyGate:
    """Fail-closed policy evaluator for orchestrator tool invocations."""

    @classmethod
    def evaluate(cls, action: Dict[str, Any]) -> PolicyVerdict:
        tool_name = str(action.get("tool_name", "")).strip()
        risk = str(action.get("risk_level", "low")).lower()
        autonomy_level = str(action.get("autonomy_level", "supervised")).lower()
        mutating = cls._is_mutating_action(action)

        if mutating:
            envelope = cls._extract_envelope(action)
            if envelope is None:
                return PolicyVerdict(False, "mutating action requires mission_envelope in payload")
            valid, reason = envelope.validate()
            if not valid:
                return PolicyVerdict(False, reason)
            if not cls._has_valid_oob_approval(action):
                return PolicyVerdict(False, "mutating action requires out-of-band approval from a different human")
            return PolicyVerdict(True, "mutating action authorized under mission envelope")

        if autonomy_level == "bounded":
            return PolicyVerdict(True, "bounded read-only action permitted after gate checks")

        if autonomy_level == "semi_autonomous":
            if "high" in risk and not cls._has_valid_oob_approval(action):
                return PolicyVerdict(False, "high-risk read requires out-of-band approval in semi_autonomous mode")
            return PolicyVerdict(True, "semi-autonomous read-only policy")

        if cls._has_valid_oob_approval(action):
            return PolicyVerdict(True, "supervised read authorized by out-of-band approval")
        return PolicyVerdict(False, "supervised mode requires out-of-band human approval")

    @staticmethod
    def _extract_envelope(action: Dict[str, Any]) -> MissionEnvelope | None:
        raw = action.get("mission_envelope")
        if raw is None:
            parameters = action.get("parameters") or {}
            if isinstance(parameters, dict):
                raw = parameters.get("mission_envelope")
        if isinstance(raw, MissionEnvelope):
            return raw
        if isinstance(raw, dict):
            try:
                return MissionEnvelope(
                    envelope_id=str(raw.get("envelope_id", "")),
                    mission_id=str(raw.get("mission_id", "")),
                    approved_by=str(raw.get("approved_by", "")),
                    scope=str(raw.get("scope", "cyber_defence")),
                    constraints=dict(raw.get("constraints") or {}),
                )
            except (TypeError, ValueError):
                return None
        return None

    @classmethod
    def _has_valid_oob_approval(cls, action: Dict[str, Any]) -> bool:
        proposer = str(
            action.get("proposer")
            or action.get("subagent_id")
            or action.get("agent_id")
            or "orchestrator"
        )
        for approval in cls._iter_approvals(action):
            if isinstance(approval, Approval):
                candidate = approval
            elif isinstance(approval, dict):
                candidate = Approval(
                    approver=str(approval.get("approver", "")),
                    proposer=str(approval.get("proposer", proposer)),
                    channel=str(approval.get("channel", "")),
                )
            else:
                continue
            if candidate.proposer == proposer and candidate.is_valid():
                return True
        return False

    @staticmethod
    def _iter_approvals(action: Dict[str, Any]) -> Iterable[Any]:
        sources: List[Any] = []
        if isinstance(action.get("approvals"), list):
            sources.extend(action["approvals"])
        parameters = action.get("parameters") or {}
        if isinstance(parameters, dict):
            if isinstance(parameters.get("approvals"), list):
                sources.extend(parameters["approvals"])
        policy_context = action.get("policy_context") or {}
        if isinstance(policy_context, dict) and isinstance(policy_context.get("approvals"), list):
            sources.extend(policy_context["approvals"])
        return sources

    @classmethod
    def _is_mutating_action(cls, action: Dict[str, Any]) -> bool:
        tool_name = str(action.get("tool_name", "")).strip()
        parameters = action.get("parameters") or {}
        if not isinstance(parameters, dict):
            parameters = {}

        if tool_name in {"file_write", "file_delete", "database_mutate"}:
            return True
        if tool_name == "git_operation":
            args = parameters.get("args")
            if isinstance(args, Sequence) and args:
                head = str(args[0]).lower()
                return head in _GIT_WRITE_SUBCOMMANDS
            return True
        if tool_name.startswith("xiid."):
            tool_class = str(parameters.get("xiid_class") or parameters.get("class") or "").upper()
            if tool_class in _XIID_MUTATING_CLASSES:
                return True
        return False


# --- SOAR playbook integration (Layer 07 cyber operations) ---


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One proposed SOAR response action presented for authority review."""

    tool_name: str
    case_id: str
    step_id: int
    step_kind: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "case_id": self.case_id,
            "step_id": self.step_id,
            "step_kind": self.step_kind,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class Approvals:
    """Commander or SOC lead approval bound to specific SOAR tool names."""

    approval_id: str
    approver: str
    approved_at: datetime
    approved_tools: List[str]
    execution_authorized: bool = True

    def covers_tool(self, tool_name: str) -> bool:
        return tool_name.upper() in {item.upper() for item in self.approved_tools}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "approver": self.approver,
            "approved_at": self.approved_at.isoformat(),
            "approved_tools": list(self.approved_tools),
            "execution_authorized": self.execution_authorized,
        }


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """SOAR-specific policy routing decision for playbook execution."""

    allowed: bool
    outcome: str
    reason: str
    tool_call: ToolCall
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "outcome": self.outcome,
            "reason": self.reason,
            "tool_call": self.tool_call.to_dict(),
            "timestamp": self.timestamp.isoformat(),
        }


def _soar_envelope_case_id(envelope: MissionEnvelope) -> str:
    constraints = envelope.constraints if isinstance(envelope.constraints, dict) else {}
    return str(constraints.get("case_id", "")).strip()


def _soar_envelope_allows_tool(envelope: MissionEnvelope, tool_name: str) -> bool:
    constraints = envelope.constraints if isinstance(envelope.constraints, dict) else {}
    allowed = constraints.get("allowed_tools")
    if not isinstance(allowed, list) or not allowed:
        return True
    return tool_name.upper() in {str(item).upper() for item in allowed}


def evaluate_soar_tool_call(
    tool_call: ToolCall,
    envelope: MissionEnvelope | None,
    approvals: Approvals | None,
    *,
    auto_execute: bool = False,
    manual_execution: bool = False,
) -> PolicyDecision:
    """Evaluate a SOAR mutate step against mission envelope and approvals."""
    if tool_call.step_kind != "mutate":
        return PolicyDecision(
            allowed=True,
            outcome="allow",
            reason="non_mutate_step",
            tool_call=tool_call,
        )

    if envelope is None:
        return PolicyDecision(
            allowed=False,
            outcome="queue",
            reason="missing_envelope",
            tool_call=tool_call,
        )

    valid, reason = envelope.validate()
    if not valid:
        return PolicyDecision(
            allowed=False,
            outcome="deny",
            reason=reason,
            tool_call=tool_call,
        )

    case_id = _soar_envelope_case_id(envelope)
    if case_id and case_id != tool_call.case_id:
        return PolicyDecision(
            allowed=False,
            outcome="deny",
            reason="envelope_case_mismatch",
            tool_call=tool_call,
        )

    if not _soar_envelope_allows_tool(envelope, tool_call.tool_name):
        return PolicyDecision(
            allowed=False,
            outcome="deny",
            reason="tool_not_in_envelope",
            tool_call=tool_call,
        )

    if approvals is None:
        return PolicyDecision(
            allowed=False,
            outcome="queue",
            reason="missing_approvals",
            tool_call=tool_call,
        )

    if not approvals.execution_authorized:
        return PolicyDecision(
            allowed=False,
            outcome="queue",
            reason="execution_not_authorized",
            tool_call=tool_call,
        )

    if not approvals.covers_tool(tool_call.tool_name):
        return PolicyDecision(
            allowed=False,
            outcome="queue",
            reason="tool_not_approved",
            tool_call=tool_call,
        )

    if not auto_execute and not manual_execution:
        return PolicyDecision(
            allowed=False,
            outcome="queue",
            reason="awaiting_approval",
            tool_call=tool_call,
        )

    return PolicyDecision(
        allowed=True,
        outcome="allow",
        reason="approved",
        tool_call=tool_call,
    )


PolicyGate.evaluate_soar = staticmethod(evaluate_soar_tool_call)  # type: ignore[method-assign]
