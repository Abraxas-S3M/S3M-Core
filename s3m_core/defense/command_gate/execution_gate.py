"""Single chokepoint execution gate for shell/tool commands.

Military/tactical context:
This gate is a hard interlock in the command path to prevent hostile or
unsafe execution flows during mission operations.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import subprocess
import time
from typing import Deque, Dict, List, Literal

from .command_parser import CommandAST, CommandParser
from .obfuscation_detector import ObfuscationDetector, ObfuscationReport
from .threat_classifier import CommandThreatClassifier, CommandThreatScore


DecisionType = Literal["approve", "deny", "escalate", "modify"]
PolicyMode = Literal["strict", "standard", "permissive"]


@dataclass(frozen=True)
class ExecutionPolicy:
    """Policy controls for runtime gate behavior."""

    mode: PolicyMode = "standard"
    auto_approve_safe: bool = True
    auto_approve_medium: bool = False
    require_human_for_critical: bool = True
    block_all_blocked: bool = True
    max_commands_per_minute: int = 30
    max_commands_per_session: int = 1000

    def __post_init__(self) -> None:
        if self.max_commands_per_minute <= 0:
            raise ValueError("max_commands_per_minute must be > 0")
        if self.max_commands_per_session <= 0:
            raise ValueError("max_commands_per_session must be > 0")


@dataclass
class GateDecision:
    """Gate decision and full evidence for auditing."""

    decision: DecisionType
    original_command: str
    parsed: CommandAST
    threat_score: CommandThreatScore
    obfuscation: ObfuscationReport
    modified_command: str | None
    reason: str
    requires_human: bool


@dataclass
class ExecutionResult:
    """Result from executing an approved command."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    resources_used: Dict[str, int | float | bool]


class ExecutionGate:
    """Evaluate and enforce command policy before execution."""

    _RISK_ORDER = {
        "safe": 0,
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
        "blocked": 5,
    }

    def __init__(
        self,
        parser: CommandParser,
        classifier: CommandThreatClassifier,
        obfuscation_detector: ObfuscationDetector,
        policy: ExecutionPolicy,
    ) -> None:
        if parser is None:
            raise ValueError("parser is required")
        if classifier is None:
            raise ValueError("classifier is required")
        if obfuscation_detector is None:
            raise ValueError("obfuscation_detector is required")
        if policy is None:
            raise ValueError("policy is required")

        self.parser = parser
        self.classifier = classifier
        self.obfuscation_detector = obfuscation_detector
        self.policy = policy

        self._history: Dict[str, List[GateDecision]] = defaultdict(list)
        self._recent_timestamps: Dict[str, Deque[float]] = defaultdict(deque)
        self._session_counts: Dict[str, int] = defaultdict(int)

    def evaluate(self, command: str, session_id: str, context: str = None) -> GateDecision:
        """Evaluate command against parser, obfuscation, classifier, and policy."""
        if command is None or not str(command).strip():
            raise ValueError("command must be a non-empty string")
        if not session_id or not str(session_id).strip():
            raise ValueError("session_id is required")

        rate_limit_reason = self._consume_rate_budget(session_id=session_id)
        parsed = self.parser.parse(command)
        obfuscation = self.obfuscation_detector.detect(command)
        threat_score = self.classifier.classify(parsed)
        decision_reason = "Command approved by default policy path."
        modified_command: str | None = None
        requires_human = False

        if obfuscation.obfuscated and obfuscation.decoded_command:
            decoded_ast = self.parser.parse(obfuscation.decoded_command)
            decoded_score = self.classifier.classify(decoded_ast)
            if self._is_higher_risk(decoded_score.overall_risk, threat_score.overall_risk):
                threat_score = decoded_score
            if decoded_score.overall_risk in {"blocked", "critical"}:
                gate_decision = GateDecision(
                    decision="deny",
                    original_command=command,
                    parsed=parsed,
                    threat_score=decoded_score,
                    obfuscation=obfuscation,
                    modified_command=None,
                    reason=(
                        f"Rejected obfuscated payload ({obfuscation.technique}); decoded command scored "
                        f"{decoded_score.overall_risk}."
                    ),
                    requires_human=False,
                )
                self._history[session_id].append(gate_decision)
                return gate_decision

        if rate_limit_reason:
            gate_decision = GateDecision(
                decision="deny",
                original_command=command,
                parsed=parsed,
                threat_score=threat_score,
                obfuscation=obfuscation,
                modified_command=None,
                reason=rate_limit_reason,
                requires_human=False,
            )
            self._history[session_id].append(gate_decision)
            return gate_decision

        if threat_score.overall_risk == "blocked" and self.policy.block_all_blocked:
            decision = "deny"
            decision_reason = "Denied: policy blocks BLOCKED command classes."
        elif threat_score.overall_risk == "critical":
            sanitized = self._attempt_sanitization(parsed)
            if sanitized is not None:
                decision = "modify"
                modified_command = sanitized
                decision_reason = "Critical command sanitized to a safer equivalent."
            elif self.policy.require_human_for_critical:
                decision = "escalate"
                requires_human = True
                decision_reason = "Critical command requires human approval."
            else:
                decision = "deny"
                decision_reason = "Critical command denied by policy."
        elif threat_score.overall_risk == "high":
            decision = "escalate"
            requires_human = True
            decision_reason = "High-risk command requires operator review."
        elif threat_score.overall_risk == "medium":
            if self.policy.auto_approve_medium or self.policy.mode == "permissive":
                decision = "approve"
                decision_reason = "Medium-risk command approved with audit logging."
            else:
                decision = "escalate"
                requires_human = True
                decision_reason = "Medium-risk command requires approval in current mode."
        elif threat_score.overall_risk == "low":
            if self.policy.mode == "strict":
                decision = "escalate"
                requires_human = True
                decision_reason = "Low-risk command escalated under strict mode."
            else:
                decision = "approve"
                decision_reason = "Low-risk command approved with monitoring."
        else:
            if self.policy.auto_approve_safe:
                decision = "approve"
                decision_reason = "Safe command auto-approved."
            else:
                decision = "escalate"
                requires_human = True
                decision_reason = "Safe command awaits manual approval by policy."

        if context and decision in {"approve", "modify"}:
            decision_reason = f"{decision_reason} Context: {context}"

        gate_decision = GateDecision(
            decision=decision,
            original_command=command,
            parsed=parsed,
            threat_score=threat_score,
            obfuscation=obfuscation,
            modified_command=modified_command,
            reason=decision_reason,
            requires_human=requires_human,
        )
        self._history[session_id].append(gate_decision)
        return gate_decision

    def execute_approved(self, command: str, session_id: str, timeout: int = 300) -> ExecutionResult:
        """Execute command only if it has an approved/modified gate decision."""
        if timeout <= 0:
            raise ValueError("timeout must be > 0")

        latest = self._latest_decision_for_command(session_id=session_id, command=command)
        if latest is None or latest.decision not in {"approve", "modify"}:
            raise PermissionError("command is not approved for execution in this session")

        command_to_run = latest.modified_command if latest.decision == "modify" else command
        start = time.monotonic()
        try:
            completed = subprocess.run(
                command_to_run,
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout,
                cwd="/workspace",
            )
            duration = time.monotonic() - start
            resources = {
                "timed_out": False,
                "stdout_bytes": len(completed.stdout.encode("utf-8")),
                "stderr_bytes": len(completed.stderr.encode("utf-8")),
            }
            return ExecutionResult(
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_seconds=duration,
                resources_used=resources,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            return ExecutionResult(
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + "\nCommand timed out.",
                duration_seconds=duration,
                resources_used={"timed_out": True, "timeout_seconds": timeout},
            )

    def get_command_history(self, session_id: str) -> List[GateDecision]:
        """Return full gate history for an execution session."""
        return list(self._history.get(session_id, []))

    def _consume_rate_budget(self, session_id: str) -> str | None:
        now = time.time()
        timestamps = self._recent_timestamps[session_id]
        while timestamps and (now - timestamps[0]) > 60:
            timestamps.popleft()

        if len(timestamps) >= self.policy.max_commands_per_minute:
            return "Denied: max commands per minute exceeded."
        if self._session_counts[session_id] >= self.policy.max_commands_per_session:
            return "Denied: max commands per session exceeded."

        timestamps.append(now)
        self._session_counts[session_id] += 1
        return None

    @classmethod
    def _is_higher_risk(cls, candidate: str, current: str) -> bool:
        return cls._RISK_ORDER[candidate] > cls._RISK_ORDER[current]

    @staticmethod
    def _attempt_sanitization(parsed: CommandAST) -> str | None:
        executable = parsed.executable.lower()
        args = parsed.arguments
        if executable == "git" and args and args[0] == "push":
            filtered = [arg for arg in args[1:] if arg not in {"--force", "-f"}]
            if len(filtered) != len(args[1:]):
                return " ".join([parsed.executable, "push", *filtered]).strip()
        return None

    def _latest_decision_for_command(self, session_id: str, command: str) -> GateDecision | None:
        history = self._history.get(session_id, [])
        for decision in reversed(history):
            if decision.original_command == command:
                return decision
        return None
