"""Runtime action gatekeeper for mission-safe S3M policy enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Literal
from urllib.parse import urlparse


ActionDecisionLabel = Literal["approve", "deny", "escalate", "force_deliberation"]


@dataclass(frozen=True)
class ActionPolicy:
    """Policy controls for a single executable action type."""

    allowed: bool
    requires_approval: bool
    max_scope: str
    cooldown_seconds: int

    def __post_init__(self) -> None:
        if not self.max_scope.strip():
            raise ValueError("max_scope must be non-empty")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")


@dataclass(frozen=True)
class EscalationRule:
    """Rule describing when an action must be escalated."""

    name: str
    action_types: tuple[str, ...] = ()
    confidence_below: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if self.confidence_below is not None and not 0.0 <= self.confidence_below <= 1.0:
            raise ValueError("confidence_below must be between 0 and 1")

    def matches(self, action_type: str, model_confidence: float) -> bool:
        action_match = not self.action_types or action_type in self.action_types
        confidence_match = (
            self.confidence_below is None or model_confidence < self.confidence_below
        )
        return action_match and confidence_match


@dataclass
class PolicyConfig:
    """Configuration container for policy gate thresholds and action controls."""

    allowed_actions: dict[str, ActionPolicy] = field(default_factory=dict)
    risk_thresholds: dict[str, float] = field(default_factory=dict)
    escalation_rules: list[EscalationRule] = field(default_factory=list)
    network_allowlist: tuple[str, ...] = ()
    external_api_allowlist: tuple[str, ...] = ()
    production_mode: bool = True

    def __post_init__(self) -> None:
        defaults = _default_action_policies()
        for action_type, default_policy in defaults.items():
            self.allowed_actions.setdefault(action_type, default_policy)

        for action_type, threshold in self.risk_thresholds.items():
            if not 0.0 <= threshold <= 1.0:
                raise ValueError(f"Risk threshold for '{action_type}' must be between 0 and 1")


@dataclass(frozen=True)
class ThreatAlert:
    """SAE threat alert emitted during action planning."""

    alert_type: str
    severity: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.alert_type.strip():
            raise ValueError("alert_type must be non-empty")
        normalized = self.severity.strip().lower()
        if normalized not in {"low", "medium", "high", "critical"}:
            raise ValueError("severity must be one of: low, medium, high, critical")


@dataclass(frozen=True)
class EmotionProfile:
    """Affective risk signal used to trigger tactical deliberation safeguards."""

    risk_flag: bool
    stress_level: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.stress_level <= 1.0:
            raise ValueError("stress_level must be between 0 and 1")


@dataclass
class ProposedAction:
    """Action proposal emitted by a model before runtime execution."""

    action_type: str
    target: str
    parameters: dict[str, Any]
    model_confidence: float
    sae_alerts: list[ThreatAlert] = field(default_factory=list)
    emotion_profile: EmotionProfile = field(default_factory=lambda: EmotionProfile(risk_flag=False))

    def __post_init__(self) -> None:
        if not self.action_type.strip():
            raise ValueError("action_type must be non-empty")
        if not self.target.strip():
            raise ValueError("target must be non-empty")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters must be a dictionary")
        if not 0.0 <= self.model_confidence <= 1.0:
            raise ValueError("model_confidence must be between 0 and 1")


@dataclass(frozen=True)
class ActionDecision:
    """Final gate decision for a proposed runtime action."""

    decision: ActionDecisionLabel
    reason: str
    required_modifications: list[str] = field(default_factory=list)


class ActionGate:
    """Runtime policy gatekeeper for tactical safety and security controls."""

    _DANGEROUS_SHELL_PATTERNS = (
        r"(^|\s)rm\s+-rf\s+/",
        r"(:\(\)\s*\{\s*:\|:\&\s*\};:)",
        r"(^|\s)mkfs(\.|$|\s)",
        r"(^|\s)dd\s+if=",
        r"(^|\s)(shutdown|reboot)(\s|$)",
        r"(^|\s)(curl|wget)\b[^\n]*\|\s*(bash|sh)",
    )
    _PRIVILEGE_ESCALATION_PATTERNS = (
        r"(^|\s)sudo(\s|$)",
        r"(^|\s)su(\s|$)",
        r"(^|\s)pkexec(\s|$)",
        r"(^|\s)setcap(\s|$)",
        r"chmod\s+\+s",
    )

    def __init__(self, policy_config: PolicyConfig):
        self.policy_config = policy_config
        self._decision_log: list[dict[str, Any]] = []

    def evaluate_action(self, action: ProposedAction) -> ActionDecision:
        """Evaluate an action proposal against policy, risk, and safety rules."""
        if self._has_critical_security_alert(action.sae_alerts):
            decision = ActionDecision(
                decision="deny",
                reason=(
                    "Denied due to critical SAE alert for security bypass or concealment; "
                    "this is a non-overridable tactical safety interlock."
                ),
                required_modifications=["log_security_incident"],
            )
            self._log_decision(action, decision)
            return decision

        policy = self.policy_config.allowed_actions.get(action.action_type)
        if policy is None:
            decision = ActionDecision(
                decision="deny",
                reason=f"Unknown action type '{action.action_type}' is denied by default.",
                required_modifications=[],
            )
            self._log_decision(action, decision)
            return decision

        decision = self._evaluate_by_action_type(action, policy)
        decision = self._apply_confidence_threshold(action, decision)
        decision = self._apply_escalation_rules(action, decision)
        decision = self._apply_deliberation_boost_if_needed(action, decision)

        self._log_decision(action, decision)
        return decision

    def get_decision_log(self) -> list[dict[str, Any]]:
        """Return immutable copy of gate decisions for audit workflows."""
        return [entry.copy() for entry in self._decision_log]

    def _evaluate_by_action_type(self, action: ProposedAction, policy: ActionPolicy) -> ActionDecision:
        action_type = action.action_type
        if not policy.allowed:
            if action_type == "credential_access":
                return ActionDecision(
                    decision="escalate",
                    reason="Credential access is denied by default and must be escalated to a human.",
                    required_modifications=["human_security_approval_required"],
                )
            return ActionDecision(
                decision="deny",
                reason=f"Action '{action_type}' is disallowed by policy.",
                required_modifications=[],
            )

        if action_type == "file_read":
            return ActionDecision("approve", "File read is low-risk and approved.", [])
        if action_type == "file_write":
            return ActionDecision(
                "approve",
                "File write approved with mandatory audit logging.",
                ["enable_write_audit_log"],
            )
        if action_type == "file_delete":
            modifications = ["confirm_delete_scope"]
            if self.policy_config.production_mode and policy.requires_approval:
                modifications.append("human_approval_required")
            return ActionDecision(
                "force_deliberation",
                "File delete is destructive and requires deliberation.",
                modifications,
            )
        if action_type == "shell_execute":
            return self._evaluate_shell_command(action)
        if action_type == "network_request":
            return self._evaluate_network_target(action.target, self.policy_config.network_allowlist)
        if action_type == "subprocess_spawn":
            return self._evaluate_subprocess(action)
        if action_type == "git_operation":
            return self._evaluate_git_operation(action)
        if action_type == "database_mutate":
            modifications = ["transactional_guardrail", "rollback_plan_required"]
            if policy.requires_approval:
                modifications.append("human_approval_required")
            return ActionDecision(
                "force_deliberation",
                "Database mutation requires deliberation and explicit approval.",
                modifications,
            )
        if action_type == "api_call_external":
            decision = self._evaluate_network_target(
                action.target, self.policy_config.external_api_allowlist
            )
            if decision.decision == "approve":
                return ActionDecision(
                    "approve",
                    f"{decision.reason} External API call will be fully logged.",
                    sorted(set(decision.required_modifications + ["log_external_api_call"])),
                )
            return decision
        return ActionDecision(
            decision="deny",
            reason=f"Action '{action_type}' has no registered evaluator and is denied.",
            required_modifications=[],
        )

    def _apply_confidence_threshold(
        self, action: ProposedAction, decision: ActionDecision
    ) -> ActionDecision:
        threshold = self.policy_config.risk_thresholds.get(action.action_type)
        if threshold is None:
            return decision
        if action.model_confidence >= threshold:
            return decision
        if decision.decision == "deny":
            return decision
        modifications = sorted(set(decision.required_modifications + ["low_confidence_review"]))
        return ActionDecision(
            decision="force_deliberation",
            reason=(
                f"{decision.reason} Model confidence {action.model_confidence:.2f} "
                f"is below required threshold {threshold:.2f}."
            ),
            required_modifications=modifications,
        )

    def _apply_escalation_rules(
        self, action: ProposedAction, decision: ActionDecision
    ) -> ActionDecision:
        if decision.decision in {"deny", "escalate"}:
            return decision
        for rule in self.policy_config.escalation_rules:
            if rule.matches(action.action_type, action.model_confidence):
                modifications = sorted(
                    set(decision.required_modifications + [f"escalation_rule:{rule.name}"])
                )
                reason = rule.reason or f"Escalation rule '{rule.name}' matched."
                return ActionDecision("escalate", reason, modifications)
        return decision

    def _apply_deliberation_boost_if_needed(
        self, action: ProposedAction, decision: ActionDecision
    ) -> ActionDecision:
        if not action.emotion_profile.risk_flag or not self._is_destructive(action):
            return decision
        if decision.decision == "deny":
            return decision
        modifications = sorted(set(decision.required_modifications + ["apply_deliberation_boost"]))
        if decision.decision == "approve":
            return ActionDecision(
                "force_deliberation",
                (
                    f"{decision.reason} Emotional risk flag is active for destructive action; "
                    "deliberation boost is required before execution."
                ),
                modifications,
            )
        return ActionDecision(decision.decision, decision.reason, modifications)

    @classmethod
    def _has_critical_security_alert(cls, alerts: list[ThreatAlert]) -> bool:
        for alert in alerts:
            alert_type = alert.alert_type.strip().lower()
            severity = alert.severity.strip().lower()
            if alert_type in {"security_bypass", "concealment"} and severity == "critical":
                return True
        return False

    @classmethod
    def _is_destructive(cls, action: ProposedAction) -> bool:
        if action.action_type in {"file_delete", "database_mutate"}:
            return True
        if action.action_type == "git_operation":
            command = str(action.parameters.get("command", "")).lower()
            return ("push --force" in command) or ("reset --hard" in command)
        if action.action_type == "shell_execute":
            command = str(action.parameters.get("command", ""))
            return cls._contains_pattern(command, cls._DANGEROUS_SHELL_PATTERNS)
        return False

    @classmethod
    def _evaluate_shell_command(cls, action: ProposedAction) -> ActionDecision:
        command = str(action.parameters.get("command", "")).strip()
        if not command:
            return ActionDecision("deny", "shell_execute requires a non-empty command.", [])
        if cls._contains_pattern(command, cls._DANGEROUS_SHELL_PATTERNS):
            return ActionDecision("deny", "Denied dangerous shell command pattern.", ["log_security_incident"])
        return ActionDecision(
            "approve",
            "Shell command approved after danger pattern scan.",
            ["log_shell_command"],
        )

    @classmethod
    def _evaluate_subprocess(cls, action: ProposedAction) -> ActionDecision:
        command = str(action.parameters.get("command", "")).strip()
        if not command:
            return ActionDecision(
                "deny",
                "subprocess_spawn requires an explicit command for policy evaluation.",
                [],
            )
        if cls._contains_pattern(command, cls._PRIVILEGE_ESCALATION_PATTERNS):
            return ActionDecision(
                "deny",
                "Subprocess denied due to privilege escalation indicators.",
                ["log_security_incident"],
            )
        return ActionDecision(
            "approve",
            "Subprocess spawn approved under current permission envelope.",
            ["log_subprocess_spawn"],
        )

    @classmethod
    def _evaluate_git_operation(cls, action: ProposedAction) -> ActionDecision:
        command = str(action.parameters.get("command", "")).strip().lower()
        if not command:
            return ActionDecision("deny", "git_operation requires a command.", [])

        forceful_ops = ("push --force", "push -f", "reset --hard")
        read_ops = ("status", "log", "show", "diff", "branch", "rev-parse", "fetch")

        if any(op in command for op in forceful_ops):
            return ActionDecision(
                "force_deliberation",
                "Forceful git operation requires deliberate review.",
                ["confirm_branch_safety", "backup_reference_before_force"],
            )
        if any(command.startswith(op) or f" git {op}" in command for op in read_ops):
            return ActionDecision("approve", "Read-only git operation approved.", [])
        return ActionDecision(
            "approve",
            "Git operation approved with audit logging.",
            ["log_git_operation"],
        )

    @staticmethod
    def _evaluate_network_target(target: str, allowlist: tuple[str, ...]) -> ActionDecision:
        if not allowlist:
            return ActionDecision(
                "deny",
                "No allowlist configured; network action denied by default.",
                ["configure_allowlist"],
            )
        host = _extract_host(target)
        if not host:
            return ActionDecision("deny", "Could not parse target host for allowlist check.", [])
        if any(_host_matches_allowlist(host, allowed) for allowed in allowlist):
            return ActionDecision(
                "approve",
                f"Target host '{host}' is allowlisted.",
                ["log_network_request"],
            )
        return ActionDecision(
            "deny",
            f"Target host '{host}' is not in allowlist.",
            ["log_denied_network_request"],
        )

    @staticmethod
    def _contains_pattern(command: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, command, flags=re.IGNORECASE) for pattern in patterns)

    def _log_decision(self, action: ProposedAction, decision: ActionDecision) -> None:
        self._decision_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action_type": action.action_type,
                "target": action.target,
                "decision": decision.decision,
                "reason": decision.reason,
            }
        )


def _default_action_policies() -> dict[str, ActionPolicy]:
    return {
        "file_read": ActionPolicy(
            allowed=True, requires_approval=False, max_scope="workspace", cooldown_seconds=0
        ),
        "file_write": ActionPolicy(
            allowed=True, requires_approval=False, max_scope="workspace", cooldown_seconds=1
        ),
        "file_delete": ActionPolicy(
            allowed=True, requires_approval=True, max_scope="workspace", cooldown_seconds=10
        ),
        "shell_execute": ActionPolicy(
            allowed=True, requires_approval=False, max_scope="sandboxed", cooldown_seconds=2
        ),
        "network_request": ActionPolicy(
            allowed=True, requires_approval=False, max_scope="allowlisted-hosts", cooldown_seconds=1
        ),
        "credential_access": ActionPolicy(
            allowed=False, requires_approval=True, max_scope="none", cooldown_seconds=60
        ),
        "subprocess_spawn": ActionPolicy(
            allowed=True, requires_approval=False, max_scope="sandboxed", cooldown_seconds=2
        ),
        "git_operation": ActionPolicy(
            allowed=True, requires_approval=False, max_scope="repository", cooldown_seconds=1
        ),
        "database_mutate": ActionPolicy(
            allowed=True, requires_approval=True, max_scope="transaction", cooldown_seconds=10
        ),
        "api_call_external": ActionPolicy(
            allowed=True, requires_approval=False, max_scope="allowlisted-apis", cooldown_seconds=1
        ),
    }


def _extract_host(target: str) -> str:
    stripped = target.strip()
    if not stripped:
        return ""
    parsed = urlparse(stripped if "://" in stripped else f"https://{stripped}")
    return (parsed.hostname or "").lower()


def _host_matches_allowlist(host: str, allowed: str) -> bool:
    normalized_allowed = allowed.strip().lower()
    if not normalized_allowed:
        return False
    return host == normalized_allowed or host.endswith(f".{normalized_allowed}")
