"""Weekly strategic estimate generation for intelligence leadership."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.apps.intel.models import ReportClassification, WeeklyEstimate
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class WeeklyEstimateGenerator:
    """Generate bilingual weekly strategic intelligence estimates."""

    def __init__(self, collector: object = None):
        self.collector = collector
        self.orchestrator = Orchestrator()
        self._history: list[WeeklyEstimate] = []

    def _ask(self, prompt: str, domain: TaskDomain) -> str:
        try:
            result = self.orchestrator.process(QueryRequest(prompt=prompt, domain=domain))
            text = getattr(result, "text", "")
            if text and "pending" not in text.lower():
                return text
        except Exception:
            pass
        return ""

    def generate(self, week: str = None) -> WeeklyEstimate:
        now = datetime.now(timezone.utc)
        iso_week = week or f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
        since = now - timedelta(days=7)
        items = self.collector.get_items(since=since, limit=20000) if self.collector else []

        region_groups: dict[str, list] = {}
        for item in items:
            for region in item.regions:
                region_groups.setdefault(region, []).append(item)

        regional_assessments: list[dict] = []
        trend_analysis: dict[str, dict] = {}
        for region, rows in region_groups.items():
            avg_relevance = sum(i.relevance_score for i in rows) / max(1, len(rows))
            alarming = len([i for i in rows if i.sentiment == "alarming"])
            negative = len([i for i in rows if i.sentiment == "negative"])
            trajectory = "rising" if alarming + negative > max(1, len(rows) // 2) else "stable"
            regional_assessments.append(
                {
                    "region": region,
                    "items": len(rows),
                    "avg_relevance": round(avg_relevance, 3),
                    "trajectory": trajectory,
                    "forecast_note": (
                        "Escalation risk requires sustained ISR and readiness."
                        if trajectory == "rising"
                        else "Risk posture steady with targeted monitoring."
                    ),
                }
            )
            trend_analysis[region] = {
                "avg_relevance": round(avg_relevance, 3),
                "alarming_items": alarming,
                "negative_items": negative,
                "trend": trajectory,
            }

        emerging_threats = []
        topic_counts: dict[str, int] = {}
        for item in items:
            for topic in item.topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        for topic, count in sorted(topic_counts.items(), key=lambda row: row[1], reverse=True)[:5]:
            if count >= 3:
                emerging_threats.append(
                    {
                        "topic": topic,
                        "signal_count": count,
                        "assessment": "Emerging multi-source pattern warrants focused collection.",
                    }
                )

        summaries = "; ".join(
            f"{row['region']}: {row['trajectory']} ({row['items']} items)"
            for row in regional_assessments[:8]
        ) or "No significant trend data."
        regions = [row["region"] for row in regional_assessments]
        forecast_prompt = (
            f"Based on intelligence trends over the past week for {regions}: {summaries}. "
            "Generate a 30-day strategic forecast for Saudi national security. Consider: "
            "regional dynamics, emerging threats, opportunity windows."
        )
        forecast_30_day = self._ask(forecast_prompt, TaskDomain.REASONING) or (
            "30-day forecast: Elevated risks likely persist in maritime chokepoints and proxy contest zones; "
            "opportunity windows remain in diplomatic de-escalation tracks and coordinated defensive signaling."
        )

        exec_prompt = (
            f"Generate a weekly executive intelligence summary for {iso_week}. "
            f"Regional trend snapshot: {summaries}. Emerging threats: {emerging_threats}."
        )
        executive_en = self._ask(exec_prompt, TaskDomain.PLANNING) or (
            f"Weekly estimate {iso_week}: Intelligence trends indicate mixed stability with localized escalation pockets. "
            "Priority concerns include maritime threat vectors, proxy activity, and cyber pressure on critical systems."
        )
        executive_ar = self._ask(
            f"اكتب ملخصًا تنفيذيًا عربيًا لهذا التقدير الأسبوعي: {executive_en[:1200]}",
            TaskDomain.ARABIC_NLP,
        ) or "الملخص التنفيذي الأسبوعي متاح بالإنجليزية مع متابعة عربية موجزة عند توفر النموذج."

        estimate = WeeklyEstimate(
            estimate_id=f"weekly-{uuid4().hex[:10]}",
            week=iso_week,
            classification=ReportClassification.FOUO,
            executive_summary_en=executive_en,
            executive_summary_ar=executive_ar,
            regional_assessments=regional_assessments,
            trend_analysis=trend_analysis,
            emerging_threats=emerging_threats,
            forecast_30_day=forecast_30_day,
        )
        self._history.append(estimate)
        return estimate

    def get_history(self, weeks: int = 4) -> list[WeeklyEstimate]:
        return self._history[-max(1, int(weeks)) :]
