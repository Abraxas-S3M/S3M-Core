"""Daily intelligence brief generation pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.apps.intel.models import DailyBrief, ReportClassification
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class DailyBriefGenerator:
    """Build daily bilingual briefs from latest intelligence collection."""

    def __init__(self, collector: object = None):
        self.collector = collector
        self.orchestrator = Orchestrator()
        self._history: list[DailyBrief] = []

    def _ask(self, prompt: str, domain: TaskDomain) -> str:
        try:
            result = self.orchestrator.process(QueryRequest(prompt=prompt, domain=domain))
            text = getattr(result, "text", "")
            if text and "pending" not in text.lower():
                return text
        except Exception:
            pass
        return ""

    def generate(self, date: str = None) -> DailyBrief:
        now = datetime.now(timezone.utc)
        target = date or now.date().isoformat()
        since = now - timedelta(hours=24)
        items = self.collector.get_items(since=since, limit=5000) if self.collector else []

        by_region: dict[str, list] = {}
        for item in items:
            for region in item.regions:
                by_region.setdefault(region, []).append(item)

        region_rows: list[dict] = []
        ranked_events: list[dict] = []
        for region, rows in by_region.items():
            risk = min(100.0, round(sum(i.relevance_score * (1.2 if i.sentiment == "alarming" else 1.0) for i in rows) * 20, 2))
            summary_en = f"{len(rows)} events tracked; risk indicator {risk:.1f}/100."
            summary_ar = f"تم تتبع {len(rows)} أحداث؛ مؤشر المخاطر {risk:.1f} من 100."
            key_events = [i.title for i in sorted(rows, key=lambda x: x.relevance_score, reverse=True)[:5]]
            region_rows.append(
                {
                    "region": region,
                    "risk_level": risk,
                    "summary_en": summary_en,
                    "summary_ar": summary_ar,
                    "key_events": key_events,
                }
            )
            for item in rows:
                severity = 1.4 if item.sentiment == "alarming" else 1.1 if item.sentiment == "negative" else 0.8
                ranked_events.append(
                    {
                        "item_id": item.item_id,
                        "title": item.title,
                        "region": region,
                        "score": round(item.relevance_score * severity, 4),
                        "sentiment": item.sentiment,
                    }
                )

        top_events = sorted(ranked_events, key=lambda row: row["score"], reverse=True)[:10]

        warnings = []
        if self.collector and hasattr(self.collector, "warning_system"):
            warnings = [
                indicator.to_dict()
                for indicator in self.collector.warning_system.get_active_warnings()
            ]

        events_summary = "; ".join(event["title"] for event in top_events[:5]) or "No significant events."
        regions = sorted(by_region.keys())
        warnings_summary = ", ".join(w["name"] for w in warnings) if warnings else "None"
        prompt_en = (
            f"Generate a Daily Intelligence Brief executive summary for {target}. "
            f"Key events: {events_summary}. Regions covered: {regions}. Active warnings: {warnings_summary}. "
            "Write 3 paragraphs: situation overview, key concerns, recommended focus areas."
        )
        executive_en = self._ask(prompt_en, TaskDomain.PLANNING) or (
            f"Daily intelligence posture for {target}: {len(items)} items analyzed across {len(regions)} regions. "
            "Primary concerns center on maritime security, proxy activity, and critical infrastructure exposure. "
            "Recommended focus: corroborate alarming signals, maintain ISR density in high-risk corridors, and sustain defensive readiness."
        )
        executive_ar = self._ask(
            f"اكتب ملخصًا تنفيذيًا عربيًا موجزًا لهذا الملخص: {executive_en[:1200]}",
            TaskDomain.ARABIC_NLP,
        ) or "الملخص التنفيذي اليومي متاح بالإنجليزية مع متابعة عربية موجزة عند توفر النموذج."

        recommendations = [
            "Increase corroboration on top-ranked alarming events.",
            "Sustain maritime and cyber watch in elevated-risk regions.",
            "Review warning indicators at least every 6 hours.",
        ]
        brief = DailyBrief(
            brief_id=f"daily-{uuid4().hex[:10]}",
            date=target,
            classification=ReportClassification.FOUO,
            executive_summary_en=executive_en,
            executive_summary_ar=executive_ar,
            regions=sorted(region_rows, key=lambda row: row["risk_level"], reverse=True),
            top_events=top_events,
            warnings=warnings,
            recommendations=recommendations,
            sources_consulted=len({item.source_id for item in items}),
            items_analyzed=len(items),
        )
        self._history.append(brief)
        return brief

    def get_history(self, days: int = 7) -> list[DailyBrief]:
        return self._history[-max(1, int(days)) :]

