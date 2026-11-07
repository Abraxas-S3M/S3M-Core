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
