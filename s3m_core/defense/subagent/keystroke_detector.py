"""Detection and interdiction for synthetic keystroke approval attacks.

Military/tactical context:
Hostile automation scripts can rapidly bypass human-in-the-loop controls;
this detector blocks those scripts before they compromise command authority.
"""

from __future__ import annotations

import logging
import os
import re
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol


@dataclass(slots=True, frozen=True)
class CommandEvent:
    """Normalized command execution event observed in one session."""

    command: str
    pid: int | None = None
    cwd: str | None = None
    source: str = "runtime"
    metadata: dict[str, Any] | None = None


@dataclass(slots=True, frozen=True)
class SimulationDetection:
    """Structured record for one blocked keystroke simulation attempt."""

    session_id: str
    command: str
    reason: str
    pid: int | None
    source: str
    context: dict[str, Any]
    timestamp: str


class ExecutionGate(Protocol):
    """Protocol for runtime execution gate integrations."""

    def block_command(self, *, session_id: str, command: str, reason: str) -> Any:
        """Block command execution with reason and session context."""


class KeystrokeSimulationDetector:
    """Detect and block synthetic input attempts that auto-approve prompts."""

    _PATTERN_DEFINITIONS = (
        ("xdotool/xte invocation", r"\b(xdotool|xte)\b"),
        ("xdg-open invocation", r"\bxdg-open\b"),
        ("/dev/input device access", r"/dev/input/"),
        ("expect automation script", r"\b(autoexpect|expect)\b"),
        ("python pynput import", r"\b(import|from)\s+pynput\b"),
        ("python pyautogui import", r"\b(import|from)\s+pyautogui\b"),
        ("echo piped to stdin", r"\becho\b[^\n|]*\|\s*(script|bash|sh|python|tmux|screen)\b"),
        ("tmux send-keys command", r"\btmux\s+send-keys\b"),
        ("screen stuff command", r"\bscreen\b[^\n]*\bstuff\b"),
        ("newline printf pipe", r"printf\s+['\"]\\n['\"]\s*\|\s*"),
        ("yes auto-approve pipe", r"(^|\s)yes\s*\|\s*"),
    )
    _PERMISSION_PROMPT_PATTERNS = (
        r"approve\s+(this\s+)?command",
        r"allow\s+(this\s+)?(action|command)",
        r"permission\s+prompt",
        r"\[y/n\]",
        r"\[y\/n\]",
        r"press\s+enter\s+to\s+continue",
    )
    _SCRIPT_FILE_SUFFIXES = {".sh", ".bash", ".py", ".zsh"}

    def __init__(
        self,
        execution_gate: ExecutionGate | Any,
        command_source: Callable[[str], Iterable[CommandEvent | Mapping[str, Any] | str]],
        *,
        process_killer: Callable[[int], None] | None = None,
        alert_sink: Callable[[dict[str, Any]], None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if not callable(command_source):
            raise ValueError("command_source must be callable")
        self.execution_gate = execution_gate
        self.command_source = command_source
        self.process_killer = process_killer
        self.alert_sink = alert_sink
        self.logger = logger or logging.getLogger("s3m.defense.keystroke_detector")
        self.detections: list[SimulationDetection] = []
        self._compiled_patterns = [
            (reason, re.compile(pattern, flags=re.IGNORECASE))
            for reason, pattern in self._PATTERN_DEFINITIONS
        ]
        self._compiled_prompt_patterns = [
            re.compile(pattern, flags=re.IGNORECASE) for pattern in self._PERMISSION_PROMPT_PATTERNS
        ]

    def monitor_for_simulation(self, session_id: str) -> None:
        """Inspect command stream and block any simulated-input attempt."""
        safe_session = str(session_id or "").strip()
        if not safe_session:
            raise ValueError("session_id must be non-empty")

        for raw_event in self.command_source(safe_session):
            event = self._normalize_event(raw_event)
            reason = self._detect_reason(event.command, cwd=event.cwd)
            if reason is None:
                continue
            self._respond_to_detection(safe_session, event, reason)

    def _respond_to_detection(self, session_id: str, event: CommandEvent, reason: str) -> None:
        self._block_via_execution_gate(session_id=session_id, command=event.command, reason=reason)
        self._kill_offending_process(event.pid)
        alert_payload = self._build_alert_payload(session_id=session_id, event=event, reason=reason)
        self._emit_alert(alert_payload)

        detection = SimulationDetection(
            session_id=session_id,
            command=event.command,
            reason=reason,
            pid=event.pid,
            source=event.source,
            context=alert_payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.detections.append(detection)
        self.logger.critical(
            "Blocked simulated keystroke attempt",
            extra={
                "session_id": session_id,
                "reason": reason,
                "command": event.command,
                "pid": event.pid,
                "source": event.source,
            },
        )

    def _detect_reason(self, command: str, *, cwd: str | None) -> str | None:
        normalized_command = str(command or "").strip()
        if not normalized_command:
            return None

        for reason, pattern in self._compiled_patterns:
            if pattern.search(normalized_command):
                return reason

        script_reason = self._scan_referenced_scripts(normalized_command, cwd=cwd)
        if script_reason:
            return script_reason
        return None

    def _scan_referenced_scripts(self, command: str, *, cwd: str | None) -> str | None:
        for token in command.split():
            candidate = token.strip("'\"")
            if not candidate:
                continue
            path = Path(candidate)
            if path.suffix.lower() not in self._SCRIPT_FILE_SUFFIXES:
                continue
            resolved = path if path.is_absolute() else (Path(cwd or ".") / path)
            if not resolved.exists() or not resolved.is_file():
                continue
            if resolved.stat().st_size > 1024 * 1024:
                continue
            if self._script_contains_prompt_pattern(resolved):
                return f"script contains permission-prompt automation markers: {resolved}"
        return None

    def _script_contains_prompt_pattern(self, path: Path) -> bool:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        lowered = content.lower()
        has_prompt_pattern = any(pattern.search(lowered) for pattern in self._compiled_prompt_patterns)
        has_auto_approve = "yes |" in lowered or "tmux send-keys" in lowered or "printf '\\n' |" in lowered
        return bool(has_prompt_pattern and has_auto_approve)

    def _block_via_execution_gate(self, *, session_id: str, command: str, reason: str) -> None:
        gate = self.execution_gate
        # Tactical fail-closed behavior: try known blocking interfaces in order.
        for method_name in ("block_command", "deny_command", "block", "deny"):
            method = getattr(gate, method_name, None)
            if callable(method):
                try:
                    method(session_id=session_id, command=command, reason=reason)
                except TypeError:
                    method(command, reason)
                return

        evaluator = getattr(gate, "evaluate_action", None)
        if callable(evaluator):
            evaluator(
                {
                    "session_id": session_id,
                    "action_type": "shell_execute",
                    "target": command,
                    "parameters": {"command": command},
                    "model_confidence": 1.0,
                    "reason": reason,
                }
            )
            return

        raise RuntimeError("execution_gate does not expose a blocking API")

    def _kill_offending_process(self, pid: int | None) -> None:
        if pid is None:
            return
        if self.process_killer is not None:
            self.process_killer(pid)
            return
        try:
            os.kill(int(pid), signal.SIGKILL)
        except OSError:
            # Defensive telemetry path: failure to kill should not hide detection.
            self.logger.exception("Failed to kill offending process", extra={"pid": pid})

    def _emit_alert(self, payload: dict[str, Any]) -> None:
        if self.alert_sink is not None:
            self.alert_sink(payload)

    @staticmethod
    def _build_alert_payload(*, session_id: str, event: CommandEvent, reason: str) -> dict[str, Any]:
        return {
            "level": "critical",
            "event_type": "keystroke_simulation_detected",
            "session_id": session_id,
            "command": event.command,
            "pid": event.pid,
            "source": event.source,
            "reason": reason,
            "context": event.metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _normalize_event(raw_event: CommandEvent | Mapping[str, Any] | str) -> CommandEvent:
        if isinstance(raw_event, CommandEvent):
            return raw_event
        if isinstance(raw_event, str):
            return CommandEvent(command=raw_event)
        if isinstance(raw_event, Mapping):
            command = str(raw_event.get("command", "")).strip()
            pid = raw_event.get("pid")
            normalized_pid = int(pid) if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()) else None
            cwd = raw_event.get("cwd")
            source = str(raw_event.get("source", "runtime"))
            metadata = dict(raw_event.get("metadata", {})) if isinstance(raw_event.get("metadata"), Mapping) else {}
            return CommandEvent(
                command=command,
                pid=normalized_pid,
                cwd=str(cwd) if cwd else None,
                source=source,
                metadata=metadata,
            )
        raise TypeError(f"Unsupported command event type: {type(raw_event)!r}")
