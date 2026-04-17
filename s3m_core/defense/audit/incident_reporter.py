"""Bilingual incident report generation for S3M security operations.

Military/tactical context:
SOC teams in multinational command structures need immediate bilingual reports
that preserve forensic evidence and remediation actions for rapid containment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence
import uuid

from .forensic_snapshot import ForensicReport, TimelineEvent
from .merkle_log import AuditEntry


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


@dataclass(slots=True, frozen=True)
class ThreatAssessment:
    """Threat-scoring payload from runtime defense evaluators."""

    severity: str
    category: str
    score: float
    summary: str
    impacted_assets: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not str(self.severity).strip():
            raise ValueError("severity must be non-empty")
        normalized = str(self.severity).strip().lower()
        if normalized not in {"low", "medium", "high", "critical"}:
            raise ValueError("severity must be one of: low, medium, high, critical")
        if not str(self.category).strip():
            raise ValueError("category must be non-empty")
        if not 0.0 <= float(self.score) <= 1.0:
            raise ValueError("score must be between 0 and 1")
        if not str(self.summary).strip():
            raise ValueError("summary must be non-empty")


@dataclass(slots=True, frozen=True)
class Evidence:
    """One evidence artifact listed in the incident package."""

    evidence_id: str
    source: str
    description: str
    reference: str
    integrity_hash: str = ""

    def __post_init__(self) -> None:
        if not str(self.evidence_id).strip():
            raise ValueError("evidence_id must be non-empty")
        if not str(self.source).strip():
            raise ValueError("source must be non-empty")
        if not str(self.description).strip():
            raise ValueError("description must be non-empty")
        if not str(self.reference).strip():
            raise ValueError("reference must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "description": self.description,
            "reference": self.reference,
            "integrity_hash": self.integrity_hash,
        }


@dataclass(slots=True, frozen=True)
class IncidentReport:
    """Full bilingual incident report emitted to SOC channels."""

    report_id: str
    severity: str
    title_en: str
    title_ar: str
    executive_summary_en: str
    executive_summary_ar: str
    technical_details: str
    timeline: List[TimelineEvent]
    evidence: List[Evidence]
    impact_assessment: str
    remediation_steps: List[str]
    lessons_learned: List[str]
    generated_at: datetime

    def __post_init__(self) -> None:
        if not str(self.report_id).strip():
            raise ValueError("report_id must be non-empty")
        if not str(self.severity).strip():
            raise ValueError("severity must be non-empty")
        for field_value, field_name in (
            (self.title_en, "title_en"),
            (self.title_ar, "title_ar"),
            (self.executive_summary_en, "executive_summary_en"),
            (self.executive_summary_ar, "executive_summary_ar"),
            (self.technical_details, "technical_details"),
            (self.impact_assessment, "impact_assessment"),
        ):
            if not str(field_value).strip():
                raise ValueError(f"{field_name} must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "severity": self.severity,
            "title_en": self.title_en,
            "title_ar": self.title_ar,
            "executive_summary_en": self.executive_summary_en,
            "executive_summary_ar": self.executive_summary_ar,
            "technical_details": self.technical_details,
            "timeline": [event.to_dict() for event in self.timeline],
            "evidence": [item.to_dict() for item in self.evidence],
            "impact_assessment": self.impact_assessment,
            "remediation_steps": list(self.remediation_steps),
            "lessons_learned": list(self.lessons_learned),
            "generated_at": _ensure_utc(self.generated_at).isoformat(),
        }


class IncidentReporter:
    """Generate and distribute bilingual incident reports."""

    def __init__(
        self,
        *,
        output_dir: str = "incident_reports",
        translators: Mapping[str, Any] | None = None,
    ) -> None:
        if not str(output_dir).strip():
            raise ValueError("output_dir must be non-empty")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.translators = dict(translators or {})

    def generate_report(
        self,
        threat_assessment: ThreatAssessment,
        forensic_report: ForensicReport,
        audit_entries: List[AuditEntry],
    ) -> IncidentReport:
        """Build a bilingual report from threat + forensic evidence."""
        if not isinstance(threat_assessment, ThreatAssessment):
            raise TypeError("threat_assessment must be ThreatAssessment")
        if not isinstance(forensic_report, ForensicReport):
            raise TypeError("forensic_report must be ForensicReport")
        if not isinstance(audit_entries, list):
            raise TypeError("audit_entries must be a list")

        report_id = f"IR-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        severity = str(threat_assessment.severity).strip().lower()
        title_en = (
            f"S3M Security Incident ({severity.upper()}): "
            f"{threat_assessment.category.replace('_', ' ').title()}"
        )
        title_ar = self._translate_to_arabic(title_en)

        executive_summary_en = (
            f"{threat_assessment.summary} Attack vector: "
            f"{forensic_report.attack_vector_identified}."
        )
        executive_summary_ar = self._translate_to_arabic(executive_summary_en)

        technical_details = self._build_technical_details(
            threat_assessment=threat_assessment,
            forensic_report=forensic_report,
            audit_entries=audit_entries,
        )
        timeline = self._merge_timeline(forensic_report.timeline, audit_entries)
        evidence = self._build_evidence(audit_entries)

        impact_assessment = self._build_impact_assessment(threat_assessment, forensic_report)
        remediation_steps = self._dedupe_preserve(
            [
                *threat_assessment.recommended_actions,
                *forensic_report.recommendations,
                "Harden execution gate policy and isolate high-risk tool paths.",
            ]
        )
        lessons_learned = self._build_lessons_learned(
            threat_assessment=threat_assessment,
            forensic_report=forensic_report,
            audit_entries=audit_entries,
        )

        return IncidentReport(
            report_id=report_id,
            severity=severity,
            title_en=title_en,
            title_ar=title_ar,
            executive_summary_en=executive_summary_en,
            executive_summary_ar=executive_summary_ar,
            technical_details=technical_details,
            timeline=timeline,
            evidence=evidence,
            impact_assessment=impact_assessment,
            remediation_steps=remediation_steps,
            lessons_learned=lessons_learned,
            generated_at=_utc_now(),
        )

    def export_pdf(self, report: IncidentReport, path: str) -> None:
        """Export report into a PDF-like artifact for SOC distribution.

        This offline-safe implementation writes a text payload with `.pdf`
        extension, preserving field structure without external dependencies.
        """
        if not isinstance(report, IncidentReport):
            raise TypeError("report must be IncidentReport")
        output_path = Path(path)
        if output_path.suffix.lower() != ".pdf":
            raise ValueError("path must end with .pdf")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "S3M INCIDENT REPORT",
            f"Report ID: {report.report_id}",
            f"Severity: {report.severity}",
            f"Generated At (UTC): {_ensure_utc(report.generated_at).isoformat()}",
            "",
            f"Title (EN): {report.title_en}",
            f"Title (AR): {report.title_ar}",
            "",
            "Executive Summary (EN):",
            report.executive_summary_en,
            "",
            "Executive Summary (AR):",
            report.executive_summary_ar,
            "",
            "Technical Details:",
            report.technical_details,
            "",
            "Impact Assessment:",
            report.impact_assessment,
            "",
            "Remediation Steps:",
        ]
        lines.extend([f"- {step}" for step in report.remediation_steps])
        lines.append("")
        lines.append("Lessons Learned:")
        lines.extend([f"- {item}" for item in report.lessons_learned])
        lines.append("")
        lines.append("Timeline:")
        for event in report.timeline:
            lines.append(
                f"- {_ensure_utc(event.timestamp).isoformat()} | {event.source} | "
                f"{event.event} | {json.dumps(event.details, ensure_ascii=False, sort_keys=True)}"
            )
        lines.append("")
        lines.append("Evidence:")
        for item in report.evidence:
            lines.append(
                f"- {item.evidence_id} | {item.source} | {item.description} | "
                f"{item.reference} | {item.integrity_hash}"
            )

        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def send_alert(self, report: IncidentReport, channels: List[str]) -> None:
        """Dispatch report alerts to configured channels.

        Supported channels: ``email``, ``slack``, ``sms``, ``dashboard``.
        Alerts are spooled locally for offline relay services.
        """
        if not isinstance(report, IncidentReport):
            raise TypeError("report must be IncidentReport")
        if not isinstance(channels, list):
            raise TypeError("channels must be a list")
        allowed = {"email", "slack", "sms", "dashboard"}
        normalized_channels = []
        for channel in channels:
            value = str(channel).strip().lower()
            if not value:
                continue
            if value not in allowed:
                raise ValueError(f"Unsupported channel: {channel}")
            normalized_channels.append(value)
        unique_channels = self._dedupe_preserve(normalized_channels)

        alerts_dir = self.output_dir / "alerts"
        alerts_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "report_id": report.report_id,
            "severity": report.severity,
            "title_en": report.title_en,
            "title_ar": report.title_ar,
            "summary_en": report.executive_summary_en,
            "summary_ar": report.executive_summary_ar,
            "generated_at": _ensure_utc(report.generated_at).isoformat(),
        }
        for channel in unique_channels:
            target_file = alerts_dir / f"{report.report_id}_{channel}.json"
            target_file.write_text(
                json.dumps({"channel": channel, "payload": payload}, indent=2, ensure_ascii=False, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )

    def _translate_to_arabic(self, text: str) -> str:
        translator = self.translators.get("en_to_ar")
        if callable(translator):
            translated = translator(text)
            if translated is not None and str(translated).strip():
                return str(translated).strip()
        # Deterministic tactical fallback when translator is unavailable.
        return f"[AR] {text}"

    @staticmethod
    def _dedupe_preserve(items: Iterable[str]) -> List[str]:
        deduped: Dict[str, str] = {}
        for item in items:
            value = str(item).strip()
            if not value:
                continue
            key = value.lower()
            if key not in deduped:
                deduped[key] = value
        return list(deduped.values())

    def _build_technical_details(
        self,
        *,
        threat_assessment: ThreatAssessment,
        forensic_report: ForensicReport,
        audit_entries: List[AuditEntry],
    ) -> str:
        lines = [
            "Threat category: " + threat_assessment.category,
            f"Threat score: {threat_assessment.score:.2f}",
            "Forensic root cause: " + forensic_report.root_cause,
            "Forensic confidence: " + f"{forensic_report.confidence:.2f}",
            "Impacted assets: " + ", ".join(threat_assessment.impacted_assets or ["unspecified"]),
            f"Audit entries reviewed: {len(audit_entries)}",
        ]
        severities = [str(entry.severity).strip().lower() for entry in audit_entries]
        if severities:
            counts: Dict[str, int] = {}
            for sev in severities:
                counts[sev] = counts.get(sev, 0) + 1
            lines.append("Audit severity distribution: " + json.dumps(counts, sort_keys=True))
        return "\n".join(lines)

    def _merge_timeline(
        self,
        forensic_timeline: Sequence[TimelineEvent],
        audit_entries: Sequence[AuditEntry],
    ) -> List[TimelineEvent]:
        merged: List[TimelineEvent] = list(forensic_timeline)
        for entry in audit_entries:
            merged.append(
                TimelineEvent(
                    timestamp=_ensure_utc(entry.timestamp),
                    event=str(entry.event_type),
                    source=str(entry.source_layer),
                    details={
                        "severity": str(entry.severity),
                        "session_id": str(entry.session_id),
                        "details": dict(entry.details),
                    },
                )
            )
        merged.sort(key=lambda item: item.timestamp)
        return merged

    def _build_evidence(self, audit_entries: Sequence[AuditEntry]) -> List[Evidence]:
        evidence: List[Evidence] = []
        for index, entry in enumerate(audit_entries, start=1):
            payload = {
                "timestamp": _ensure_utc(entry.timestamp).isoformat(),
                "session_id": entry.session_id,
                "event_type": entry.event_type,
                "source_layer": entry.source_layer,
                "severity": entry.severity,
                "details": entry.details,
                "previous_hash": entry.previous_hash,
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            integrity_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            evidence.append(
                Evidence(
                    evidence_id=f"EV-{index:04d}",
                    source=str(entry.source_layer),
                    description=f"{entry.event_type} ({entry.severity})",
                    reference=f"session:{entry.session_id}",
                    integrity_hash=integrity_hash,
                )
            )
        if not evidence:
            evidence.append(
                Evidence(
                    evidence_id="EV-0000",
                    source="forensic_snapshot",
                    description="No audit entries available at report time.",
                    reference="snapshot-only",
                    integrity_hash="",
                )
            )
        return evidence

    @staticmethod
    def _build_impact_assessment(
        threat_assessment: ThreatAssessment,
        forensic_report: ForensicReport,
    ) -> str:
        assets = threat_assessment.impacted_assets or forensic_report.data_compromised
        scope = ", ".join(str(item) for item in assets[:10]) if assets else "unknown scope"
        return (
            f"Severity {threat_assessment.severity.upper()} with estimated impact score "
            f"{threat_assessment.score:.2f}. Potentially affected assets: {scope}."
        )

    @staticmethod
    def _build_lessons_learned(
        *,
        threat_assessment: ThreatAssessment,
        forensic_report: ForensicReport,
        audit_entries: Sequence[AuditEntry],
    ) -> List[str]:
        lessons = [
            "Immutable audit evidence is essential for post-incident trust restoration.",
            "ExecutionGate and EgressProxy telemetry must remain continuously correlated.",
            "Containment should trigger before confidence degrades below policy thresholds.",
        ]
        if forensic_report.confidence < 0.5:
            lessons.append(
                "Forensic confidence was limited; improve sensor fidelity and timeline coverage."
            )
        if any(str(entry.severity).strip().lower() == "critical" for entry in audit_entries):
            lessons.append("Critical events require automated war-room escalation playbooks.")
        if threat_assessment.category.lower() not in {"policy_bypass", "credential_access"}:
            lessons.append(
                "Expand threat taxonomy mappings to improve bilingual operator brief clarity."
            )
        return lessons
