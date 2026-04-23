"""Cross-layer threat correlation for unified session risk assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from s3m_core.policy.action_gate import ThreatAlert

from .anomaly_detector import AnomalyScore
from .attack_patterns import PatternMatch
from .sequence_analyzer import SequenceAlert


@dataclass(frozen=True)
class ProcAccessAlert:
    """Process-access alert emitted by proc guard controls."""

    alert_type: str
    severity: str
    detail: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class FileChangeEvent:
    """File integrity event from monitored filesystem paths."""

    path: str
    operation: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    detail: str = ""


@dataclass(frozen=True)
class TrafficEntry:
    """Network telemetry record from egress monitoring."""

    destination: str
    protocol: str = "tcp"
    bytes_sent: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = ""


@dataclass(frozen=True)
class Evidence:
    """Correlated evidence fragment supporting final threat assessment."""

    source: str
    detail: str
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source must be non-empty")
        if not self.detail.strip():
            raise ValueError("detail must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class ThreatAssessment:
    """Unified threat assessment for one execution session."""

    session_id: str
    timestamp: datetime
    overall_risk: str
    threat_narrative: str
    threat_narrative_ar: str
    active_patterns: list[PatternMatch]
    correlated_evidence: list[Evidence]
    recommended_actions: list[str]
    auto_response_taken: str | None

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        if self.overall_risk not in {"green", "yellow", "orange", "red", "black"}:
            raise ValueError("overall_risk must be one of green/yellow/orange/red/black")


class ThreatCorrelator:
    """Merge detections from policy, process, file, network, and behavior layers."""

    _RISK_TO_LEVEL = {
        0: "green",
        1: "yellow",
        2: "orange",
        3: "red",
        4: "black",
    }
    _SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    _AUTO_RESPONSE = {
        "green": "continue monitoring",
        "yellow": "increase monitoring frequency, log extra detail",
        "orange": "apply deliberation_boost steering, notify operator",
        "red": "pause agent execution, preserve full state, notify operator",
        "black": "kill session immediately, preserve forensic snapshot, alert security team",
    }

    def __init__(self) -> None:
        self._last_assessment: ThreatAssessment | None = None

    def correlate(
        self,
        session_id: str,
        sae_alerts: list[ThreatAlert],
        proc_alerts: list[ProcAccessAlert],
        file_events: list[FileChangeEvent],
        network_events: list[TrafficEntry],
        command_history: list[Any],
        sequence_alerts: list[SequenceAlert],
        anomaly_score: AnomalyScore,
    ) -> ThreatAssessment:
        """Correlate all detection streams into one tactical threat verdict."""
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be non-empty")

        risk_rank = 0
        evidence: list[Evidence] = []
        active_patterns: list[PatternMatch] = []
        recommended_actions: set[str] = set()

        for sequence_alert in sequence_alerts:
            if sequence_alert.pattern_name == "none" or sequence_alert.confidence <= 0:
                continue
            risk_rank = max(risk_rank, self._risk_from_label(sequence_alert.risk_level))
            active_patterns.append(
                PatternMatch(
                    pattern_id=self._pattern_id_from_name(sequence_alert.pattern_name),
                    rule_id="sequence-analyzer",
                    confidence=sequence_alert.confidence,
                    evidence=(
                        f"{sequence_alert.pattern_name} matched commands "
                        f"{sequence_alert.matching_commands}."
                    ),
                )
            )
            evidence.append(
                Evidence(
                    source="sequence_analyzer",
                    detail=(
                        f"{sequence_alert.pattern_name} ({sequence_alert.mythos_reference}) "
                        f"confidence={sequence_alert.confidence:.2f}"
                    ),
                    confidence=sequence_alert.confidence,
                )
            )
            recommended_actions.add(sequence_alert.recommended_action)

        if anomaly_score.overall >= 0.8:
            risk_rank = max(risk_rank, 2)
            evidence.append(
                Evidence(
                    source="anomaly_detector",
                    detail=f"Overall anomaly score is {anomaly_score.overall:.2f} (>0.8 threshold).",
                    confidence=min(1.0, anomaly_score.overall),
                )
            )
        elif anomaly_score.overall >= 0.6:
            risk_rank = max(risk_rank, 1)

        for dimension, score in anomaly_score.dimensions.items():
            if score >= 0.7:
                evidence.append(
                    Evidence(
                        source="anomaly_detector",
                        detail=f"Anomaly dimension '{dimension}' elevated at {score:.2f}.",
                        confidence=score,
                    )
                )

        if self._has_cross_layer_low_signal_correlation(
            sae_alerts=sae_alerts,
            proc_alerts=proc_alerts,
            file_events=file_events,
            network_events=network_events,
        ):
            risk_rank = max(risk_rank, 2)
            evidence.append(
                Evidence(
                    source="cross_layer_correlation",
                    detail="Multiple low-severity signals correlated across layers in close time window.",
                    confidence=0.78,
                )
            )
            recommended_actions.add("Escalate monitoring due to correlated low-level signals.")

        concealment = any("concealment" in alert.alert_type.lower() for alert in sae_alerts)
        git_modification = self._has_git_history_modification(file_events, command_history)
        if concealment and git_modification:
            risk_rank = max(risk_rank, 4)
            evidence.append(
                Evidence(
                    source="critical_rule",
                    detail='SAE "concealment" co-occurred with git history modification activity.',
                    confidence=0.96,
                )
            )
            active_patterns.append(
                PatternMatch(
                    pattern_id="T10",
                    rule_id="concealment-plus-git",
                    confidence=0.96,
                    evidence="Concealment and git history tampering indicate cover-up behavior.",
                )
            )
            recommended_actions.add("Freeze repository write access and preserve full forensic chain.")

        credential_extraction = any(
            "credential_extraction" in alert.alert_type.lower() for alert in sae_alerts
        )
        proc_targeting = any(
            "/proc" in alert.detail.lower() or "proc" in alert.alert_type.lower()
            for alert in proc_alerts
        )
        if credential_extraction and proc_targeting:
            risk_rank = max(risk_rank, 4)
            evidence.append(
                Evidence(
                    source="critical_rule",
                    detail='SAE "credential_extraction" combined with /proc access attempt.',
                    confidence=0.98,
                )
            )
            active_patterns.append(
                PatternMatch(
                    pattern_id="T11",
                    rule_id="credential-plus-proc",
                    confidence=0.98,
                    evidence="Credential theft indicators aligned with process introspection activity.",
                )
            )
            recommended_actions.add("Immediately revoke active credentials and terminate session.")

        network_anomaly = anomaly_score.dimensions.get("network_targets", 0.0) >= 0.7
        file_aggregation = self._has_file_aggregation(file_events, command_history)
        encoding_behavior = self._has_encoding_behavior(command_history)
        if network_anomaly and file_aggregation and encoding_behavior:
            risk_rank = max(risk_rank, 3)
            evidence.append(
                Evidence(
                    source="exfiltration_rule",
                    detail="Network anomaly plus file aggregation and encoding indicates exfiltration chain.",
                    confidence=0.93,
                )
            )
            active_patterns.append(
                PatternMatch(
                    pattern_id="T12",
                    rule_id="network-aggregation-encoding",
                    confidence=0.93,
                    evidence="Data staging and outbound anomaly aligned temporally.",
                )
            )
            recommended_actions.add("Block egress immediately and quarantine staged archives.")

        if self._has_blocked_retry_in_new_context(command_history):
            risk_rank = max(risk_rank, 2)
            evidence.append(
                Evidence(
                    source="execution_gate_correlation",
                    detail="Blocked command was retried after context switch, signaling persistence.",
                    confidence=0.84,
                )
            )
            recommended_actions.add("Disable context-switch retries for denied commands.")

        overall_risk = self._RISK_TO_LEVEL.get(risk_rank, "green")
        auto_response_taken = self._AUTO_RESPONSE[overall_risk]
        recommended_actions.add(auto_response_taken)

        threat_narrative = self._build_narrative(
            session_id=session_id,
            overall_risk=overall_risk,
            evidence=evidence,
            active_patterns=active_patterns,
        )
        threat_narrative_ar = self._build_narrative_ar(
            session_id=session_id,
            overall_risk=overall_risk,
            evidence_count=len(evidence),
        )

        assessment = ThreatAssessment(
            session_id=session_id,
            timestamp=datetime.now(timezone.utc),
            overall_risk=overall_risk,
            threat_narrative=threat_narrative,
            threat_narrative_ar=threat_narrative_ar,
            active_patterns=active_patterns,
            correlated_evidence=evidence,
            recommended_actions=sorted(recommended_actions),
            auto_response_taken=auto_response_taken,
        )
        self._last_assessment = assessment
        return assessment

    def _risk_from_label(self, risk_label: str) -> int:
        label = risk_label.lower().strip()
        if label == "critical":
            return 3
        if label == "high":
            return 2
        if label == "medium":
            return 1
        return 0

    def _pattern_id_from_name(self, pattern_name: str) -> str:
        normalized = pattern_name.lower()
        if "credential hunt" in normalized:
            return "T04-T05"
        if "sandbox reconnaissance" in normalized:
            return "T01"
        if "privilege escalation" in normalized:
            return "T07-T08"
        if "track covering" in normalized:
            return "T10"
        if "subagent escalation" in normalized:
            return "T08-T09"
        if "data staging" in normalized:
            return "T12"
        if "mcp manipulation" in normalized:
            return "T11"
        return "UNKNOWN"

    def _has_cross_layer_low_signal_correlation(
        self,
        sae_alerts: list[ThreatAlert],
        proc_alerts: list[ProcAccessAlert],
        file_events: list[FileChangeEvent],
        network_events: list[TrafficEntry],
    ) -> bool:
        low_layers: dict[str, list[datetime]] = {}
        for alert in sae_alerts:
            if alert.severity.lower() == "low":
                low_layers.setdefault("sae", []).append(datetime.now(timezone.utc))
        for alert in proc_alerts:
            if alert.severity.lower() == "low":
                low_layers.setdefault("proc", []).append(alert.timestamp)
        for event in file_events:
            if event.operation.lower() in {"read", "scan", "list"}:
                low_layers.setdefault("file", []).append(event.timestamp)
        for event in network_events:
            if event.bytes_sent <= 2048:
                low_layers.setdefault("network", []).append(event.timestamp)

        if len(low_layers.keys()) < 3:
            return False
        timestamps = [stamp for stamps in low_layers.values() for stamp in stamps]
        if not timestamps:
            return False
        return (max(timestamps) - min(timestamps)).total_seconds() <= 180

    def _has_git_history_modification(
        self, file_events: list[FileChangeEvent], command_history: list[Any]
    ) -> bool:
        for event in file_events:
            path = event.path.lower()
            operation = event.operation.lower()
            if ".git" in path or "gitignore" in path:
                if operation in {"modify", "delete", "rewrite", "rename"}:
                    return True
        for command in command_history:
            text = self._extract_command_text(command)
            if "git checkout" in text or "git reset" in text or "reflog" in text:
                return True
            if ".gitignore" in text and any(token in text for token in ("echo", "sed", "tee")):
                return True
        return False

    def _has_file_aggregation(
        self, file_events: list[FileChangeEvent], command_history: list[Any]
    ) -> bool:
        for event in file_events:
            lowered = f"{event.path} {event.operation}".lower()
            if any(token in lowered for token in (".tar", ".zip", ".7z", "archive")):
                return True
        for command in command_history:
            text = self._extract_command_text(command)
            if "tar " in text or "zip " in text or "7z " in text:
                return True
        return False

    def _has_encoding_behavior(self, command_history: list[Any]) -> bool:
        for command in command_history:
            text = self._extract_command_text(command)
            if "base64" in text or "gzip" in text or "openssl enc" in text:
                return True
        return False

    def _has_blocked_retry_in_new_context(self, command_history: list[Any]) -> bool:
        normalized: list[tuple[str, str, bool]] = []
        for entry in command_history:
            text = self._extract_command_text(entry)
            decision = self._extract_field(entry, "decision").lower()
            context = self._extract_field(entry, "context").lower()
            blocked = decision in {"deny", "denied", "blocked"} or "permission denied" in text
            normalized.append((text, context, blocked))

        blocked_commands: list[tuple[int, str, str]] = []
        for idx, (text, context, blocked) in enumerate(normalized):
            if blocked:
                blocked_commands.append((idx, text, context))

        for blocked_idx, blocked_text, blocked_context in blocked_commands:
            anchor = self._command_anchor(blocked_text)
            for idx in range(blocked_idx + 1, len(normalized)):
                text, context, _ = normalized[idx]
                if not text:
                    continue
                switched_context = context != blocked_context and (
                    "tmux" in text or "subagent" in text or "screen" in text or "context" in text
                )
                retry_same_action = anchor and anchor in self._command_anchor(text)
                if switched_context or retry_same_action:
                    return True
        return False

    @staticmethod
    def _command_anchor(text: str) -> str:
        tokens = [token for token in text.split() if token and not token.startswith("-")]
        return " ".join(tokens[:2]).strip()

    @staticmethod
    def _extract_field(obj: Any, field_name: str) -> str:
        if isinstance(obj, dict):
            return str(obj.get(field_name, "") or "")
        return str(getattr(obj, field_name, "") or "")

    def _extract_command_text(self, command: Any) -> str:
        text = self._extract_field(command, "command")
        action_type = self._extract_field(command, "action_type")
        target = self._extract_field(command, "target")
        raw = self._extract_field(command, "raw")
        params = command.get("parameters", {}) if isinstance(command, dict) else getattr(command, "parameters", {})
        if isinstance(params, dict):
            text = text or str(params.get("command", ""))
            if not target:
                target = str(params.get("target", ""))
        combined = f"{action_type} {text} {target} {raw}".strip().lower()
        return " ".join(combined.split())

    def _build_narrative(
        self,
        session_id: str,
        overall_risk: str,
        evidence: list[Evidence],
        active_patterns: list[PatternMatch],
    ) -> str:
        if not evidence:
            return (
                f"Session {session_id} remains at {overall_risk.upper()} risk with no correlated "
                "cross-layer threat indicators."
            )
        top_evidence = "; ".join(item.detail for item in evidence[:3])
        pattern_summary = ", ".join(match.pattern_id for match in active_patterns[:4]) or "no taxonomy pattern"
        return (
            f"Session {session_id} assessed as {overall_risk.upper()} risk. Active pattern signals: "
            f"{pattern_summary}. Correlated evidence: {top_evidence}."
        )

    def _build_narrative_ar(self, session_id: str, overall_risk: str, evidence_count: int) -> str:
        risk_ar = {
            "green": "أخضر",
            "yellow": "أصفر",
            "orange": "برتقالي",
            "red": "أحمر",
            "black": "أسود",
        }.get(overall_risk, "أخضر")
        return (
            f"تم تقييم الجلسة {session_id} بمستوى تهديد {risk_ar} "
            f"استنادًا إلى {evidence_count} مؤشرات مترابطة."
        )

