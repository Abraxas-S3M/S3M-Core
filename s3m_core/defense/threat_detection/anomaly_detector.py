"""Behavioral anomaly scoring for previously unseen tactical attack behavior."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import re
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class SessionLog:
    """Normalized session log for baseline and anomaly analysis."""

    session_id: str
    started_at: datetime
    ended_at: datetime
    commands: list[Any] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must be >= started_at")
        if self.errors < 0:
            raise ValueError("errors must be >= 0")


@dataclass(frozen=True)
class AnomalyScore:
    """Composite anomaly result for one session."""

    overall: float
    dimensions: dict[str, float]
    anomalous_events: list[str]

    def __post_init__(self) -> None:
        if not 0.0 <= self.overall <= 1.0:
            raise ValueError("overall must be between 0 and 1")
        required = {
            "command_rate",
            "command_types",
            "file_access",
            "network_targets",
            "error_rate",
            "privilege_attempts",
        }
        missing = required - set(self.dimensions.keys())
        if missing:
            raise ValueError(f"dimensions missing required keys: {sorted(missing)}")
        for value in self.dimensions.values():
            if not 0.0 <= value <= 1.0:
                raise ValueError("all dimension scores must be between 0 and 1")


class BehavioralAnomalyDetector:
    """Statistical detector for novel adversary behaviors not covered by signatures."""

    _COMMAND_TYPE_KEYS = ("reads", "writes", "network", "other")

    def __init__(self, baseline_sessions: int = 100):
        if baseline_sessions <= 0:
            raise ValueError("baseline_sessions must be > 0")
        self.baseline_sessions = int(baseline_sessions)
        self._baseline_ready = False
        self._baseline: dict[str, Any] = {}

    def build_baseline(self, clean_sessions: list[SessionLog]) -> None:
        """Compute baseline distributions from known-clean sessions."""
        if not isinstance(clean_sessions, list) or not clean_sessions:
            raise ValueError("clean_sessions must be a non-empty list")

        sample = [self._coerce_session(item) for item in clean_sessions[: self.baseline_sessions]]

        command_rates: list[float] = []
        type_counters: list[Counter[str]] = []
        directory_counter: Counter[str] = Counter()
        network_counter: Counter[str] = Counter()
        error_rates: list[float] = []
        session_durations: list[float] = []
        privilege_rates: list[float] = []

        for session in sample:
            commands = self._extract_command_texts(session)
            duration_minutes = max(1.0 / 60.0, self._duration_minutes(session))
            command_rates.append(len(commands) / duration_minutes)
            session_durations.append(duration_minutes)

            type_counter = self._command_type_distribution(commands)
            type_counters.append(type_counter)

            for directory in self._extract_working_directories(commands):
                directory_counter[directory] += 1

            for host in self._extract_network_targets(commands, session.events):
                network_counter[host] += 1

            observed_errors = self._observed_error_count(session, commands)
            error_rates.append(observed_errors / max(1, len(commands)))

            privilege_count = sum(1 for command in commands if self._is_privilege_command(command))
            privilege_rates.append(privilege_count / max(1, len(commands)))

        baseline_type_counter = Counter[str]()
        for counter in type_counters:
            baseline_type_counter.update(counter)

        self._baseline = {
            "command_rate_mean": self._mean(command_rates),
            "command_rate_std": self._std(command_rates),
            "command_type_distribution": self._normalize_counter(baseline_type_counter),
            "common_directories": set(directory_counter.keys()),
            "network_distribution": self._normalize_counter(network_counter),
            "error_rate_mean": self._mean(error_rates),
            "error_rate_std": self._std(error_rates),
            "session_duration_mean": self._mean(session_durations),
            "session_duration_std": self._std(session_durations),
            "privilege_rate_mean": self._mean(privilege_rates),
            "privilege_rate_std": self._std(privilege_rates),
            "n_sessions": len(sample),
        }
        self._baseline_ready = True

    def score_session(self, session: SessionLog) -> AnomalyScore:
        """Score one session against previously learned baseline behavior."""
        if not self._baseline_ready:
            raise RuntimeError("baseline is not built; call build_baseline first")
        normalized_session = self._coerce_session(session)

        commands = self._extract_command_texts(normalized_session)
        command_count = max(1, len(commands))
        duration_minutes = max(1.0 / 60.0, self._duration_minutes(normalized_session))
        command_rate = command_count / duration_minutes

        command_type_counter = self._command_type_distribution(commands)
        command_type_distribution = self._normalize_counter(command_type_counter)

        accessed_dirs = self._extract_working_directories(commands)
        network_targets = self._extract_network_targets(commands, normalized_session.events)
        error_rate = self._observed_error_count(normalized_session, commands) / command_count
        privilege_rate = (
            sum(1 for command in commands if self._is_privilege_command(command)) / command_count
        )

        command_rate_score = self._z_to_score(
            command_rate,
            self._baseline["command_rate_mean"],
            self._baseline["command_rate_std"],
        )
        command_types_score = self._js_divergence(
            command_type_distribution,
            self._baseline["command_type_distribution"],
        )
        file_access_score = self._novelty_ratio(accessed_dirs, self._baseline["common_directories"])
        network_distribution = self._normalize_counter(Counter(network_targets))
        network_targets_score = max(
            self._novelty_ratio(set(network_targets), set(self._baseline["network_distribution"].keys())),
            self._js_divergence(network_distribution, self._baseline["network_distribution"]),
        )
        error_rate_score = self._z_to_score(
            error_rate,
            self._baseline["error_rate_mean"],
            self._baseline["error_rate_std"],
        )
        privilege_attempts_score = self._z_to_score(
            privilege_rate,
            self._baseline["privilege_rate_mean"],
            self._baseline["privilege_rate_std"],
        )

        dimensions = {
            "command_rate": command_rate_score,
            "command_types": command_types_score,
            "file_access": file_access_score,
            "network_targets": network_targets_score,
            "error_rate": error_rate_score,
            "privilege_attempts": privilege_attempts_score,
        }

        weighted_overall = (
            (dimensions["command_rate"] * 0.18)
            + (dimensions["command_types"] * 0.18)
            + (dimensions["file_access"] * 0.18)
            + (dimensions["network_targets"] * 0.18)
            + (dimensions["error_rate"] * 0.14)
            + (dimensions["privilege_attempts"] * 0.14)
        )
        overall = max(0.0, min(1.0, weighted_overall))

        anomalies: list[str] = []
        if command_rate_score > 0.7:
            anomalies.append("Command activity rate deviates significantly from clean baseline.")
        if command_types_score > 0.7:
            anomalies.append("Command type mix is atypical for mission profile.")
        if file_access_score > 0.7:
            anomalies.append("Session touched unusual working directories.")
        if network_targets_score > 0.7:
            anomalies.append("Session contacted unusual network destinations.")
        if error_rate_score > 0.7:
            anomalies.append("Error rate spike indicates probing or trial-and-error behavior.")
        if privilege_attempts_score > 0.7:
            anomalies.append("Privilege escalation command rate is abnormally high.")

        return AnomalyScore(overall=overall, dimensions=dimensions, anomalous_events=anomalies)

    def _coerce_session(self, session: SessionLog | dict[str, Any]) -> SessionLog:
        if isinstance(session, SessionLog):
            return session
        if not isinstance(session, dict):
            raise TypeError("session must be SessionLog or dict")

        started_at = self._parse_datetime(session.get("started_at")) or datetime.now(timezone.utc)
        ended_at = self._parse_datetime(session.get("ended_at")) or started_at
        if ended_at < started_at:
            ended_at = started_at

        metadata = session.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        return SessionLog(
            session_id=str(session.get("session_id", "")).strip() or "unknown-session",
            started_at=started_at,
            ended_at=ended_at,
            commands=list(session.get("commands", [])) if isinstance(session.get("commands", []), list) else [],
            events=list(session.get("events", [])) if isinstance(session.get("events", []), list) else [],
            errors=int(session.get("errors", 0)) if str(session.get("errors", 0)).isdigit() else 0,
            metadata=metadata,
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _extract_command_texts(self, session: SessionLog) -> list[str]:
        commands: list[str] = []
        for item in session.commands:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = str(item.get("command") or item.get("raw") or item.get("action_type") or "").strip()
            else:
                text = str(getattr(item, "command", "")).strip()
            if text:
                commands.append(text.lower())

        for event in session.events:
            if not isinstance(event, dict):
                continue
            text = str(event.get("command", "")).strip().lower()
            if text:
                commands.append(text)

        return commands

    def _command_type_distribution(self, commands: list[str]) -> Counter[str]:
        counter = Counter[str]()
        for command in commands:
            counter[self._classify_command_type(command)] += 1
        for key in self._COMMAND_TYPE_KEYS:
            counter.setdefault(key, 0)
        return counter

    @staticmethod
    def _classify_command_type(command: str) -> str:
        if re.search(r"\b(cat|less|more|grep|find|ls|head|tail|rg)\b", command):
            return "reads"
        if re.search(r"\b(echo|tee|sed|vim|nano|cp|mv|rm|chmod|chown|touch)\b", command):
            return "writes"
        if re.search(r"\b(curl|wget|ssh|scp|nc|ping|traceroute|nmap|rsync)\b", command):
            return "network"
        return "other"

    @staticmethod
    def _extract_working_directories(commands: list[str]) -> set[str]:
        directories: set[str] = set()
        for command in commands:
            for match in re.findall(r"(/[A-Za-z0-9._/\-]+)", command):
                normalized = match.strip()
                if not normalized.startswith("/"):
                    continue
                parts = normalized.split("/")
                if len(parts) >= 3:
                    directories.add("/" + "/".join(parts[1:3]))
                elif len(parts) == 2:
                    directories.add("/" + parts[1])
        return directories

    def _extract_network_targets(self, commands: list[str], events: list[dict[str, Any]]) -> list[str]:
        hosts: list[str] = []
        for command in commands:
            for token in command.split():
                if token.startswith("http://") or token.startswith("https://"):
                    parsed = urlparse(token)
                    if parsed.hostname:
                        hosts.append(parsed.hostname.lower())
        for event in events:
            if not isinstance(event, dict):
                continue
            target = str(event.get("network_target") or event.get("destination") or "").strip()
            if not target:
                continue
            parsed = urlparse(target if "://" in target else f"https://{target}")
            if parsed.hostname:
                hosts.append(parsed.hostname.lower())
        return hosts

    @staticmethod
    def _observed_error_count(session: SessionLog, commands: list[str]) -> int:
        errors = int(session.errors)
        for command in commands:
            if any(marker in command for marker in ("error", "failed", "permission denied", "not found")):
                errors += 1
        for event in session.events:
            if isinstance(event, dict) and str(event.get("error", "")).strip():
                errors += 1
        return errors

    @staticmethod
    def _is_privilege_command(command: str) -> bool:
        return bool(re.search(r"\b(sudo|su|pkexec|doas|chmod\s+\+s|setcap)\b", command))

    @staticmethod
    def _duration_minutes(session: SessionLog) -> float:
        delta_seconds = max(1.0, (session.ended_at - session.started_at).total_seconds())
        return delta_seconds / 60.0

    @staticmethod
    def _mean(values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def _std(values: list[float]) -> float:
        if len(values) <= 1:
            return 0.01
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return max(0.01, math.sqrt(variance))

    @staticmethod
    def _normalize_counter(counter: Counter[str]) -> dict[str, float]:
        total = float(sum(counter.values()))
        if total <= 0:
            return {}
        return {key: value / total for key, value in counter.items()}

    @staticmethod
    def _z_to_score(value: float, mean: float, std: float) -> float:
        z_score = abs((value - mean) / max(std, 0.01))
        return max(0.0, min(1.0, z_score / 3.0))

    @staticmethod
    def _novelty_ratio(observed: set[str], baseline: set[str]) -> float:
        if not observed:
            return 0.0
        if not baseline:
            return 1.0
        unseen = [value for value in observed if value not in baseline]
        return max(0.0, min(1.0, len(unseen) / len(observed)))

    def _js_divergence(self, p_dist: dict[str, float], q_dist: dict[str, float]) -> float:
        keys = set(p_dist.keys()) | set(q_dist.keys())
        if not keys:
            return 0.0
        p = {key: max(1e-9, p_dist.get(key, 0.0)) for key in keys}
        q = {key: max(1e-9, q_dist.get(key, 0.0)) for key in keys}
        p_sum = sum(p.values())
        q_sum = sum(q.values())
        p = {key: value / p_sum for key, value in p.items()}
        q = {key: value / q_sum for key, value in q.items()}
        m = {key: 0.5 * (p[key] + q[key]) for key in keys}
        divergence = 0.5 * self._kl_divergence(p, m) + 0.5 * self._kl_divergence(q, m)
        return max(0.0, min(1.0, divergence))

    @staticmethod
    def _kl_divergence(p_dist: dict[str, float], q_dist: dict[str, float]) -> float:
        total = 0.0
        for key in p_dist:
            total += p_dist[key] * math.log2(p_dist[key] / max(1e-9, q_dist.get(key, 1e-9)))
        return max(0.0, total)

