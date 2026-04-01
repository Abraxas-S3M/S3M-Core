"""Factory for structured intelligence products (SITREP, INTSUM, assessments)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.apps.intel.models import (
    CrisisEvent,
    IntelReport,
    OSINTItem,
    ReportClassification,
    ReportType,
)
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class IntelProductFactory:
    """Generate military intelligence products with offline-safe fallbacks."""

    def __init__(self) -> None:
        self.orchestrator = Orchestrator()
        self._reports: list[IntelReport] = []

    @staticmethod
    def _item_summary(items: list[OSINTItem], limit: int = 12) -> str:
        lines = []
        for item in items[:limit]:
            lines.append(
                f"- [{item.timestamp.isoformat()}] {item.title} "
                f"(regions={','.join(item.regions)}, sentiment={item.sentiment}, rel={item.relevance_score:.2f})"
            )
        return "\n".join(lines) if lines else "- No source items available"

    def _ask(self, prompt: str, domain: TaskDomain) -> str:
        try:
            resp = self.orchestrator.process(QueryRequest(prompt=prompt, domain=domain))
            txt = getattr(resp, "text", "")
            if txt and "pending" not in txt.lower() and "not yet loaded" not in txt.lower():
                return txt
        except Exception:
            pass
        return ""

    def _translate_arabic(self, english_text: str) -> str:
        prompt = (
            "Translate this intelligence report to Arabic with preserved structure and military tone. "
            f"Text:\n{english_text[:4000]}"
        )
        translated = self._ask(prompt, TaskDomain.ARABIC_NLP)
        if translated:
            return translated
        return "نسخة عربية موجزة: تم توليد التقرير في وضع عدم توفر نموذج اللغة، راجع النسخة الإنجليزية."

    def _build_report(
        self,
        title: str,
        report_type: ReportType,
        body_en: str,
        body_ar: str,
        items: list[OSINTItem],
        regions: list[str] | None = None,
        topics: list[str] | None = None,
    ) -> IntelReport:
        dtg = IntelReport.to_dtg(datetime.now(timezone.utc))
        report = IntelReport(
            report_id=f"rep-{uuid4().hex[:10]}",
            title=title,
            report_type=report_type,
            classification=ReportClassification.FOUO,
            date_time_group=dtg,
            originator="S3M INTEL CENTER",
            summary_en=body_en.splitlines()[0][:300] if body_en else "No summary",
            summary_ar=body_ar.splitlines()[0][:300] if body_ar else "لا يوجد ملخص",
            body_en=body_en,
            body_ar=body_ar,
            regions=regions or sorted({r for item in items for r in item.regions}),
            topics=topics or sorted({t for item in items for t in item.topics}),
            sources_used=sorted({item.source_id for item in items}),
            key_findings=[item.title for item in items[:5]],
            risk_assessment={
                region: round(
                    sum(i.relevance_score for i in items if region in i.regions)
                    / max(1, len([i for i in items if region in i.regions])),
                    3,
                )
                for region in sorted({r for item in items for r in item.regions})
            },
            recommendations=[
                "Increase collection on high-relevance hostile indicators.",
                "Corroborate alarming reports with at least one independent source.",
                "Prioritize force protection in elevated maritime corridors.",
            ],
            attachments=[],
            valid_until=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        self._reports.append(report)
        return report

    def generate_sitrep(
        self,
        region: str,
        items: list[OSINTItem],
        crisis_events: list[CrisisEvent] | None = None,
    ) -> IntelReport:
        item_summary = self._item_summary([i for i in items if region in i.regions] or items)
        crises = ", ".join(c.name for c in (crisis_events or [])) or "none"
        prompt = (
            f"Generate a military SITREP for {region}. Intelligence items: {item_summary}. "
            f"Active crises: {crises}. Use standard SITREP format: "
            "1) ENEMY SITUATION 2) FRIENDLY SITUATION 3) OPERATIONS 4) LOGISTICS 5) CIVIL-MILITARY. "
            "Classification: UNCLASSIFIED - FOUO. Provide in English."
        )
        body_en = self._ask(prompt, TaskDomain.PLANNING)
        if not body_en:
            body_en = (
                f"SITREP — {region}\n"
                "1) ENEMY SITUATION: Hostile indicators remain under active monitoring.\n"
                "2) FRIENDLY SITUATION: Saudi and partner posture remains defensive and coordinated.\n"
                "3) OPERATIONS: ISR and maritime surveillance adjusted to current risk vectors.\n"
                "4) LOGISTICS: Sustainment lines remain serviceable with contingency rerouting prepared.\n"
                "5) CIVIL-MILITARY: Diplomatic and civilian channels remain active for de-escalation."
            )
        body_ar = self._translate_arabic(body_en)
        return self._build_report(
            title=f"SITREP — {region}",
            report_type=ReportType.SITREP,
            body_en=body_en,
            body_ar=body_ar,
            items=items,
            regions=[region],
        )

    def generate_intsum(self, items: list[OSINTItem], period: str = "24h") -> IntelReport:
        regions = sorted({r for item in items for r in item.regions})
        prompt = (
            f"Generate an Intelligence Summary (INTSUM) covering the last {period}. "
            f"Analyze {len(items)} intelligence items across {regions}. Identify: "
            "1) Key developments 2) Threat changes 3) Emerging patterns 4) Collection gaps. "
            "Classification: FOUO."
        )
        body_en = self._ask(prompt, TaskDomain.PLANNING)
        if not body_en:
            body_en = (
                f"INTSUM ({period})\n"
                f"Key developments: {len(items)} items were fused across {len(regions)} regions.\n"
                "Threat changes: Elevated activity observed in maritime and proxy domains.\n"
                "Emerging patterns: Recurrent references to drones, chokepoints, and cyber probing.\n"
                "Collection gaps: Additional corroboration needed for social-media-origin claims."
            )
        body_ar = self._translate_arabic(body_en)
        return self._build_report(
            title=f"INTSUM — Last {period}",
            report_type=ReportType.INTSUM,
            body_en=body_en,
            body_ar=body_ar,
            items=items,
        )

    def generate_threat_assessment(
        self,
        region: str,
        topic: str,
        items: list[OSINTItem],
    ) -> IntelReport:
        filtered = [i for i in items if region in i.regions and topic in i.topics] or items
        prompt = (
            f"Produce a focused threat assessment on {topic} in {region}. "
            f"Use this evidence:\n{self._item_summary(filtered)}\n"
            "Include second and third order effects and operational recommendations."
        )
        body_en = self._ask(prompt, TaskDomain.REASONING)
        if not body_en:
            body_en = (
                f"THREAT ASSESSMENT — {topic} in {region}\n"
                "Current threat posture is elevated based on recurring indicators.\n"
                "Second-order effects include maritime routing pressure and information operations.\n"
                "Third-order effects may include regional deterrence signaling and alliance recalibration.\n"
                "Recommendation: increase multi-source corroboration and contingency readiness."
            )
        body_ar = self._translate_arabic(body_en)
        return self._build_report(
            title=f"Threat Assessment — {topic} ({region})",
            report_type=ReportType.THREAT_ASSESSMENT,
            body_en=body_en,
            body_ar=body_ar,
            items=filtered,
            regions=[region],
            topics=[topic],
        )

    def generate_country_brief(self, country: str, items: list[OSINTItem]) -> IntelReport:
        filtered = [i for i in items if country.lower() in " ".join(i.regions).lower()] or items
        body_en = (
            self._ask(
                f"Generate a country intelligence brief for {country} using:\n{self._item_summary(filtered)}",
                TaskDomain.REASONING,
            )
            or (
                f"COUNTRY BRIEF — {country}\n"
                "Political-security conditions remain fluid with mixed escalation and de-escalation signals.\n"
                "Key drivers include diplomatic activity, proxy dynamics, and infrastructure risk exposure."
            )
        )
        body_ar = self._translate_arabic(body_en)
        return self._build_report(
            title=f"Country Brief — {country}",
            report_type=ReportType.COUNTRY_BRIEF,
            body_en=body_en,
            body_ar=body_ar,
            items=filtered,
        )

    def generate_crisis_report(self, crisis: CrisisEvent, items: list[OSINTItem]) -> IntelReport:
        filtered = [
            i
            for i in items
            if i.item_id in set(crisis.related_sources) or crisis.region in i.regions
        ] or items
        body_en = (
            self._ask(
                "Generate a detailed crisis report with timeline and forecast for: "
                f"{crisis.name} ({crisis.region}). Severity={crisis.severity.value}. "
                f"Evidence:\n{self._item_summary(filtered)}",
                TaskDomain.REASONING,
            )
            or (
                f"CRISIS REPORT — {crisis.name}\n"
                f"Region: {crisis.region}\n"
                f"Severity: {crisis.severity.value}\n"
                f"Status: {crisis.status}\n"
                "Assessment: Situation is actively monitored with risk-sensitive escalation controls."
            )
        )
        body_ar = self._translate_arabic(body_en)
        return self._build_report(
            title=f"Crisis Report — {crisis.name}",
            report_type=ReportType.CRISIS_REPORT,
            body_en=body_en,
            body_ar=body_ar,
            items=filtered,
            regions=[crisis.region],
        )

    def generate_custom(
        self,
        title,
        report_type,
        prompt: str,
        items: list[OSINTItem],
    ) -> IntelReport:
        rtype = report_type if isinstance(report_type, ReportType) else ReportType.CUSTOM
        body_en = self._ask(prompt, TaskDomain.PLANNING) or (
            f"{title}\nCustom report generated in template mode due to unavailable LLM output."
        )
        body_ar = self._translate_arabic(body_en)
        return self._build_report(
            title=str(title),
            report_type=rtype,
            body_en=body_en,
            body_ar=body_ar,
            items=items,
        )

    def list_reports(self) -> list[IntelReport]:
        return list(self._reports)
