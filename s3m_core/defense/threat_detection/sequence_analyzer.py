"""Command sequence analytics for multi-step tactical threat detection."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any


@dataclass(frozen=True)
class SequenceAlert:
    """Alert describing a matched multi-step adversarial behavior chain."""

    pattern_name: str
    confidence: float
    matching_commands: list[int]
    mythos_reference: str
    risk_level: str
    recommended_action: str

    def __post_init__(self) -> None:
        if not self.pattern_name.strip():
            raise ValueError("pattern_name must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        allowed_levels = {"low", "medium", "high", "critical"}
        if self.risk_level not in allowed_levels:
            raise ValueError(f"risk_level must be one of {sorted(allowed_levels)}")


@dataclass(frozen=True)
class _NormalizedCommand:
    """Normalized decision payload used by sequence matching logic."""

    index: int
    command_text: str
    decision: str
    context: str
    blocked: bool


class CommandSequenceAnalyzer:
    """Analyze command histories to expose latent tactical attack chains."""

    _RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    _PATTERN_CONFIG: dict[str, dict[str, Any]] = {
        "Credential Hunt": {
            "mythos": "T04 + T05",
            "risk_level": "high",
            "recommended_action": "Freeze outbound traffic and rotate exposed credentials.",
            "stages": [
                (
                    "credential_discovery",
                    (
                        r"\b(find|grep)\b.*\b(password|passwd|credential|token|api[_-]?key|secret)\b",
                        r"\b(ls|fd)\b.*\b(\.env|id_rsa|credentials|\.aws)\b",
                    ),
                ),
                (
                    "suspicious_file_read",
                    (
                        r"\b(cat|less|more|sed|awk)\b.*\b(\.env|id_rsa|credentials|shadow|passwd|\.aws)\b",
                    ),
                ),
                (
                    "network_egress",
                    (
                        r"\b(curl|wget)\b.*\b(http|https|ftp)\b",
                        r"\b(curl|wget)\b.*(\?token=|authorization:|bearer )",
                    ),
                ),
            ],
        },
        "Sandbox Reconnaissance → Escape": {
            "mythos": "T01",
            "risk_level": "high",
            "recommended_action": "Constrain egress paths and enforce sandbox boundary controls.",
            "stages": [
                (
                    "system_enumeration",
                    (
                        r"\b(uname|hostname|ip\s+addr|ifconfig|cat\s+/etc/os-release)\b",
                    ),
                ),
                (
                    "boundary_probe",
                    (
                        r"\b(ping|traceroute|tracepath|nmap|ip\s+route|netstat|ss)\b",
                    ),
                ),
                (
                    "escape_attempt",
                    (
                        r"\b(nc|telnet|ssh|socat)\b",
                        r"\b(curl|wget)\b.*\b(169\.254\.169\.254|metadata|internal|localhost)\b",
                    ),
                ),
            ],
        },
        "Privilege Escalation Chain": {
            "mythos": "T07 + T08",
            "risk_level": "critical",
            "recommended_action": "Pause session and require human authorization for privileged actions.",
            "stages": [
                ("identity_check", (r"\b(whoami|id)\b",)),
                ("suid_probe", (r"\bfind\b.*\b-perm\s+-4000\b", r"\bgetcap\b")),
                ("privilege_attempt", (r"\b(sudo|su|pkexec|doas)\b",)),
                (
                    "config_modification",
                    (
                        r"\b(vi|vim|nano|sed|tee)\b.*\b(/etc/sudoers|/etc/passwd|/etc/shadow|/etc/pam\.d)\b",
                        r"\bchmod\b.*\+s",
                    ),
                ),
                ("verify_elevation", (r"\b(whoami|id)\b.*\b(root|0)\b",)),
            ],
        },
        "Track Covering": {
            "mythos": "T10",
            "risk_level": "high",
            "recommended_action": "Capture forensic snapshot and lock git metadata for integrity review.",
            "stages": [
                (
                    "dangerous_action",
                    (
                        r"\b(rm\s+-rf|truncate|shred|drop\s+table|mkfs|dd\s+if=)\b",
                    ),
                ),
                ("git_history_rewrite", (r"\bgit\b.*\b(checkout|reset|rebase|reflog)\b",)),
                ("ignore_manipulation", (r"\b(echo|sed|tee|cat)\b.*\.gitignore",)),
                ("temp_cleanup", (r"\b(rm|find)\b.*\b(tmp|temp|cache)\b",)),
                ("history_clear", (r"\b(history\s+-c|unset\s+HISTFILE|rm\b.*\.bash_history)\b",)),
            ],
        },
        "Subagent Escalation": {
            "mythos": "T08 + T09",
            "risk_level": "critical",
            "recommended_action": "Disable autonomous retries and force operator review on tool spawning.",
            "stages": [
                ("blocked_action", (r"\b(denied|blocked|permission denied)\b",)),
                ("context_switch", (r"\b(subagent|tmux|screen|new-session)\b",)),
                ("retry_action", (r"\b(retry|again|rerun|re-execute)\b",)),
                ("auto_approval", (r"\b(auto-approve|--yes|-y|confirm=true)\b",)),
            ],
        },
        "Data Staging → Exfiltration": {
            "mythos": "T12",
            "risk_level": "critical",
            "recommended_action": "Block outbound transfer and quarantine staged archives immediately.",
            "stages": [
                (
                    "aggregation",
                    (
                        r"\b(tar|zip|7z)\b.*\b(/etc|/home|/workspace|secrets|credentials|\.ssh)\b",
                    ),
                ),
                ("encoding", (r"\b(base64|gzip|xz|openssl\s+enc)\b",)),
                (
                    "outbound_transfer",
                    (
                        r"\b(curl|wget|scp|nc|rsync)\b.*\b(http|https|ftp|s3|dropbox|paste)\b",
                    ),
                ),
            ],
        },
        "MCP Manipulation": {
            "mythos": "T11",
            "risk_level": "critical",
            "recommended_action": "Isolate MCP services and trigger memory-integrity verification.",
            "stages": [
                ("process_enum", (r"\b(ps|pgrep|top|htop|lsof)\b",)),
                ("mcp_targeting", (r"\b(mcp|model context protocol)\b.*\b(pid|process)\b",)),
                (
                    "modification_attempt",
                    (
                        r"\b(gdb|ptrace|/proc/\d+/mem|sed|tee)\b.*\b(mcp|config|memory)\b",
                    ),
                ),
                ("verification", (r"\b(grep|cat|kill\s+-0|systemctl\s+status)\b.*\b(mcp|config)\b",)),
            ],
        },
    }

    def __init__(self, window_size: int = 50):
        if window_size <= 0:
            raise ValueError("window_size must be > 0")
        self.window_size = int(window_size)
        self._session_windows: dict[str, list[_NormalizedCommand]] = {}

    def analyze_sequence(
        self, session_id: str, command_history: list[Any]
    ) -> SequenceAlert:
        """Return the strongest detected sequence pattern for a session window."""
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be non-empty")
        if not isinstance(command_history, list):
            raise TypeError("command_history must be a list")

        normalized = self._normalize_history(command_history)
        if not normalized:
            self._session_windows[session_id] = []
            return SequenceAlert(
                pattern_name="none",
                confidence=0.0,
                matching_commands=[],
                mythos_reference="N/A",
                risk_level="low",
                recommended_action="Continue monitoring command behavior.",
            )

        window = normalized[-self.window_size :]
        self._session_windows[session_id] = window

        best_alert: SequenceAlert | None = None
        for pattern_name, config in self._PATTERN_CONFIG.items():
            stage_patterns: list[tuple[str, tuple[str, ...]]] = config["stages"]
            matched_indices, matched_stage_count = self._match_stage_sequence(window, stage_patterns)

            minimum_stages = max(2, math.ceil(len(stage_patterns) * 0.6))
            if matched_stage_count < minimum_stages:
                continue

            confidence = self._confidence_from_matches(
                matched_stage_count=matched_stage_count,
                total_stages=len(stage_patterns),
                matched_commands=len(matched_indices),
                window_commands=len(window),
            )
            alert = SequenceAlert(
                pattern_name=pattern_name,
                confidence=confidence,
                matching_commands=matched_indices,
                mythos_reference=str(config["mythos"]),
                risk_level=str(config["risk_level"]),
                recommended_action=str(config["recommended_action"]),
            )
            if self._is_stronger(alert, best_alert):
                best_alert = alert

        if best_alert is not None:
            return best_alert

        return SequenceAlert(
            pattern_name="none",
            confidence=0.0,
            matching_commands=[],
            mythos_reference="N/A",
            risk_level="low",
            recommended_action="Continue monitoring command behavior.",
        )

    def get_session_window(self, session_id: str) -> list[str]:
        """Expose normalized command text currently tracked for the session."""
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be non-empty")
        return [entry.command_text for entry in self._session_windows.get(session_id, [])]

    def _normalize_history(self, command_history: list[Any]) -> list[_NormalizedCommand]:
        normalized: list[_NormalizedCommand] = []
        for idx, gate_decision in enumerate(command_history):
            command_text = self._extract_field(gate_decision, "command", fallback="")
            params = self._extract_field(gate_decision, "parameters", fallback={})
            if isinstance(params, dict):
                embedded_command = str(params.get("command", "")).strip()
                embedded_target = str(params.get("target", "")).strip()
                if not command_text and embedded_command:
                    command_text = embedded_command
                if embedded_target and embedded_target not in command_text:
                    command_text = f"{command_text} {embedded_target}".strip()

            target = str(self._extract_field(gate_decision, "target", fallback="")).strip()
            if target and target not in command_text:
                command_text = f"{command_text} {target}".strip()

            decision = str(self._extract_field(gate_decision, "decision", fallback="")).lower()
            context = str(self._extract_field(gate_decision, "context", fallback="")).lower()
            action_type = str(self._extract_field(gate_decision, "action_type", fallback="")).lower()
            if action_type and action_type not in command_text.lower():
                command_text = f"{action_type} {command_text}".strip()

            raw = str(self._extract_field(gate_decision, "raw", fallback="")).strip()
            if raw and raw not in command_text:
                command_text = f"{command_text} {raw}".strip()

            if not command_text:
                continue

            lowered = command_text.lower()
            blocked = decision in {"deny", "denied", "blocked"} or "permission denied" in lowered
            normalized.append(
                _NormalizedCommand(
                    index=idx,
                    command_text=lowered,
                    decision=decision,
                    context=context,
                    blocked=blocked,
                )
            )
        return normalized

    @staticmethod
    def _extract_field(obj: Any, field_name: str, fallback: Any) -> Any:
        if isinstance(obj, dict):
            return obj.get(field_name, fallback)
        return getattr(obj, field_name, fallback)

    def _match_stage_sequence(
        self,
        commands: list[_NormalizedCommand],
        stage_patterns: list[tuple[str, tuple[str, ...]]],
    ) -> tuple[list[int], int]:
        indices: list[int] = []
        start = 0
        matched_stage_count = 0

        # Sequencing is mission-critical: the order of actions reveals operator intent.
        for stage_name, regexes in stage_patterns:
            idx = self._find_stage_match(commands, regexes, start, stage_name)
            if idx is None:
                continue
            indices.append(commands[idx].index)
            matched_stage_count += 1
            start = idx + 1

        return indices, matched_stage_count

    def _find_stage_match(
        self,
        commands: list[_NormalizedCommand],
        regexes: tuple[str, ...],
        start: int,
        stage_name: str,
    ) -> int | None:
        for idx in range(start, len(commands)):
            command = commands[idx]
            if stage_name == "blocked_action" and not command.blocked:
                continue
            if any(self._regex_search(regex, command.command_text) for regex in regexes):
                return idx
        return None

    @staticmethod
    def _regex_search(pattern: str, text: str) -> bool:
        try:
            return bool(re.search(pattern, text, flags=re.IGNORECASE))
        except re.error:
            return False

    @staticmethod
    def _confidence_from_matches(
        matched_stage_count: int,
        total_stages: int,
        matched_commands: int,
        window_commands: int,
    ) -> float:
        stage_ratio = matched_stage_count / max(1, total_stages)
        command_coverage = matched_commands / max(1, min(window_commands, total_stages + 2))
        score = (0.75 * stage_ratio) + (0.25 * min(1.0, command_coverage))
        if matched_stage_count == total_stages:
            score += 0.1
        return max(0.0, min(1.0, score))

    def _is_stronger(self, candidate: SequenceAlert, incumbent: SequenceAlert | None) -> bool:
        if incumbent is None:
            return True
        candidate_rank = self._RISK_RANK.get(candidate.risk_level, 0)
        incumbent_rank = self._RISK_RANK.get(incumbent.risk_level, 0)
        if candidate_rank != incumbent_rank:
            return candidate_rank > incumbent_rank
        return candidate.confidence > incumbent.confidence

