"""Aggregate monitoring signals and issue tactical alert decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import AlertDecision, Transcript


class MonitoringAlertSystem:
    """
    Fuse monitor outputs and choose green/yellow/orange/red operator posture.

    Tactical context:
    Cross-source fusion prevents a single blind spot from allowing unsafe model
    behavior to progress during time-sensitive operations.
    """

    AUTO_ACTIONS = {
        "green": "log only",
        "yellow": "log + increase monitoring frequency",
        "orange": "log + apply deliberation_boost steering + notify operator",
        "red": "log + HALT execution + notify operator + preserve full state",
    }

    def __init__(
        self,
        *,
        transcript_logger: Any = None,
        recursive_summarizer: Any = None,
        behavior_classifier: Any = None,
        sae_monitor: Any = None,
        av_monitor: Any = None,
        emotion_probe: Any = None,
    ) -> None:
        self.transcript_logger = transcript_logger
        self.recursive_summarizer = recursive_summarizer
        self.behavior_classifier = behavior_classifier
        self.sae_monitor = sae_monitor
        self.av_monitor = av_monitor
        self.emotion_probe = emotion_probe
        self._decision_history: List[Dict[str, Any]] = []

    def process_alerts(self, session_id: str) -> AlertDecision:
        """Aggregate all sources and return one alert decision."""
        safe_session = str(session_id or "").strip()
        if not safe_session:
            raise ValueError("session_id must be a non-empty string")

        transcript = self._get_transcript(safe_session)
        sources: List[str] = []
        source_scores: List[Tuple[str, int, str]] = []

        sae_score, sae_summary = self._score_external_source("sae_monitor", self.sae_monitor, safe_session, transcript)
        if sae_score >= 0:
            source_scores.append(("sae_monitor", sae_score, sae_summary))
            if sae_score >= 4:
                sources.append("sae_monitor")

        av_score, av_summary = self._score_external_source("av_monitor", self.av_monitor, safe_session, transcript)
        if av_score >= 0:
            source_scores.append(("av_monitor", av_score, av_summary))
            if av_score >= 4:
                sources.append("av_monitor")

        emotion_score, emotion_summary = self._score_external_source(
            "emotion_probe",
            self.emotion_probe,
            safe_session,
            transcript,
        )
        if emotion_score >= 0:
            source_scores.append(("emotion_probe", emotion_score, emotion_summary))
            if emotion_score >= 4:
                sources.append("emotion_probe")

        if self.behavior_classifier is not None and transcript.turns:
            classifications = self.behavior_classifier.classify(transcript)
            behavior_score = self._score_behavior_classifications(classifications)
            behavior_summary = f"{len(classifications)} behavior categories flagged"
            source_scores.append(("behavior_classifier", behavior_score, behavior_summary))
            if behavior_score >= 4:
                sources.append("behavior_classifier")

        if self.recursive_summarizer is not None and transcript.turns:
            summary = self.recursive_summarizer.summarize_transcript(transcript)
            report = self.recursive_summarizer.evaluate_summary(summary)
            source_scores.append(
                (
                    "recursive_summarizer",
                    int(report.concern_level),
                    f"summary flags: {', '.join(report.categories) or 'none'}",
                )
            )
            if int(report.concern_level) >= 4:
                sources.append("recursive_summarizer")

        if not source_scores:
            source_scores.append(("monitoring_baseline", 0, "no source signals available"))

        level = self._derive_level(source_scores)
        recommended_action = self._derive_recommended_action(level, source_scores)
        auto_action = self.AUTO_ACTIONS[level]
        summary = self._build_summary(source_scores, transcript=transcript)

        decision = AlertDecision(
            level=level,
            sources=sorted(set(sources)),
            summary=summary,
            recommended_action=recommended_action,
            auto_action_taken=auto_action,
        )
        self._decision_history.append(
            {
                "session_id": safe_session,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "decision": decision.to_dict(),
                "source_scores": source_scores,
            }
        )
        return decision

    def _get_transcript(self, session_id: str) -> Transcript:
        if self.transcript_logger is None:
            return Transcript(session_id=session_id, turns=[])
        return self.transcript_logger.get_transcript(session_id)

    def _score_external_source(
        self,
        source_name: str,
        source: Any,
        session_id: str,
        transcript: Transcript,
    ) -> Tuple[int, str]:
        if source is None:
            return -1, f"{source_name} unavailable"
        payload = self._invoke_source(source, session_id, transcript)
        return self._normalize_source_payload(payload)

    @staticmethod
    def _invoke_source(source: Any, session_id: str, transcript: Transcript) -> Any:
        for method_name in ("assess_session", "get_signal", "evaluate", "run"):
            if hasattr(source, method_name):
                method = getattr(source, method_name)
                return method(session_id=session_id, transcript=transcript)
        if callable(source):
            return source(session_id=session_id, transcript=transcript)
        return source

    @staticmethod
    def _normalize_source_payload(payload: Any) -> Tuple[int, str]:
        if isinstance(payload, (int, float)):
            score = max(0, min(10, int(payload)))
            return score, f"numeric score {score}"

        if isinstance(payload, str):
            lowered = payload.lower()
            if "critical" in lowered or "red" in lowered:
                return 9, payload
            if "warning" in lowered or "orange" in lowered:
                return 7, payload
            if "caution" in lowered or "yellow" in lowered:
                return 4, payload
            return 2, payload

        if isinstance(payload, dict):
            if "concern_level" in payload:
                score = int(payload["concern_level"])
            elif "risk_score" in payload:
                score = int(payload["risk_score"])
            elif "score" in payload:
                score = int(payload["score"])
            elif "level" in payload:
                score = MonitoringAlertSystem._score_from_level(str(payload["level"]))
            else:
                score = 0
            summary = str(payload.get("summary") or payload.get("message") or "dict payload")
            return max(0, min(10, score)), summary

        return 0, "unrecognized source payload"

    @staticmethod
    def _score_behavior_classifications(classifications: Sequence[Any]) -> int:
        if not classifications:
            return 0
        score = 0
        for item in classifications:
            severity = str(getattr(item, "severity", "benign")).lower()
            confidence = float(getattr(item, "confidence", 0.0))
            if severity == "critical":
                score = max(score, min(10, int(7 + confidence * 3)))
            elif severity == "concerning":
                score = max(score, min(8, int(4 + confidence * 3)))
            else:
                score = max(score, min(3, int(1 + confidence * 2)))
        return score

    @staticmethod
    def _score_from_level(level: str) -> int:
        normalized = str(level).strip().lower()
        mapping = {
            "green": 1,
            "yellow": 4,
            "orange": 7,
            "red": 10,
            "critical": 10,
            "high": 8,
            "medium": 5,
            "low": 2,
        }
        return mapping.get(normalized, 0)

    @staticmethod
    def _derive_level(source_scores: Sequence[Tuple[str, int, str]]) -> str:
        max_score = max(score for _, score, _ in source_scores)
        high_sources = sum(1 for _, score, _ in source_scores if score >= 7)
        critical_sources = sum(1 for _, score, _ in source_scores if score >= 9)

        if max_score >= 9 or critical_sources >= 2:
            return "red"
        if max_score >= 7 or high_sources >= 2:
            return "orange"
        if max_score >= 4:
            return "yellow"
        return "green"

    def _derive_recommended_action(self, level: str, source_scores: Sequence[Tuple[str, int, str]]) -> str:
        top_source, top_score, top_summary = max(source_scores, key=lambda item: item[1])
        if level == "red":
            return (
                f"Immediately halt execution and preserve full state; highest-risk source "
                f"{top_source} reported score {top_score} ({top_summary})."
            )
        if level == "orange":
            return (
                f"Apply deliberation_boost steering and notify operator; source "
                f"{top_source} reported score {top_score}."
            )
        if level == "yellow":
            return (
                f"Increase monitoring cadence and schedule analyst review due to "
                f"{top_source} score {top_score}."
            )
        return "Continue logging-only posture and monitor for trend changes."

    @staticmethod
    def _build_summary(source_scores: Sequence[Tuple[str, int, str]], transcript: Transcript) -> str:
        ranked = sorted(source_scores, key=lambda item: item[1], reverse=True)[:3]
        ranked_text = "; ".join(f"{name}={score} ({summary})" for name, score, summary in ranked)
        return (
            f"Session {transcript.session_id}: analyzed {len(transcript.turns)} turns. "
            f"Top signals: {ranked_text}."
        )

