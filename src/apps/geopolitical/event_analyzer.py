"""Event analysis for geopolitical risk operations."""

from __future__ import annotations

import re
from typing import Any, List, Optional

from src.apps._shared import as_list, contains_arabic, ensure_non_empty_text, safe_float, utc_now_iso
from src.llm_core import Orchestrator, QueryRequest, TaskDomain


class EventAnalyzer:
    """Analyze geopolitical events with Saudi security context."""

    def __init__(self):
        self.orchestrator = Orchestrator()
        self.history: List[dict[str, Any]] = []

    def _ask_llm(self, prompt: str, domain: TaskDomain) -> str:
        try:
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=domain))
            text = getattr(response, "text", "") or ""
            return str(text)
        except Exception:
            return ""

    def _fallback(self, event_description: str, region: Optional[str]) -> dict:
        return {
            "event": event_description,
            "region": region,
            "impact": "UNKNOWN",
            "escalation_likelihood_pct": 0.0,
            "recommended_posture": "Maintain monitoring posture and validate additional intelligence.",
            "second_order_effects": [],
            "third_order_effects": [],
            "indicators_to_watch": [],
            "raw_analysis": "Analysis unavailable — LLM not loaded",
            "timestamp": utc_now_iso(),
        }

    def _parse_impact(self, text: str) -> str:
        up = text.upper()
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            if level in up:
                return level
        return "UNKNOWN"

    def _parse_percentage(self, text: str) -> float:
        m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", text)
        if not m:
            return 0.0
        return max(0.0, min(100.0, safe_float(m.group(1), 0.0)))

    def _parse_list(self, text: str, marker: str) -> List[str]:
        lines = [line.strip(" -•\t") for line in text.splitlines()]
        start = -1
        marker_lower = marker.lower()
        for idx, line in enumerate(lines):
            if marker_lower in line.lower():
                start = idx + 1
                break
        if start < 0:
            return []
        out: List[str] = []
        for line in lines[start:]:
            if not line:
                continue
            if re.match(r"^\d+\)", line):
                break
            out.append(line)
            if len(out) >= 5:
                break
        return out

    def analyze(self, event_description: str, region: str = None) -> dict:
        desc = ensure_non_empty_text(event_description, "event_description")
        region_value = region.strip() if isinstance(region, str) and region.strip() else None
        prompt = (
            "Analyze this geopolitical event from the perspective of Saudi national security: "
            f"'{desc}'. Region: {region_value or 'Unspecified'}. "
            "Provide: 1) Impact assessment on Saudi interests (LOW/MEDIUM/HIGH/CRITICAL) "
            "2) Likelihood of escalation (percentage) 3) Recommended posture adjustment "
            "4) Second-order effects 5) Third-order effects 6) Key indicators to watch. "
            "Classification: UNCLASSIFIED - FOUO."
        )
        raw = self._ask_llm(prompt, TaskDomain.REASONING)
        if not raw or "pending - engine not yet loaded" in raw.lower():
            result = self._fallback(desc, region_value)
            self.history.append(result)
            return result
        result = {
            "event": desc,
            "region": region_value,
            "impact": self._parse_impact(raw),
            "escalation_likelihood_pct": self._parse_percentage(raw),
            "recommended_posture": self._parse_list(raw, "Recommended posture")[0]
            if self._parse_list(raw, "Recommended posture")
            else "Adjust posture based on threat progression indicators.",
            "second_order_effects": self._parse_list(raw, "Second-order"),
            "third_order_effects": self._parse_list(raw, "Third-order"),
            "indicators_to_watch": self._parse_list(raw, "indicators"),
            "raw_analysis": raw,
            "timestamp": utc_now_iso(),
        }
        self.history.append(result)
        return result

    def analyze_arabic(self, event_description: str, region: str = None) -> dict:
        desc = ensure_non_empty_text(event_description, "event_description")
        region_value = region.strip() if isinstance(region, str) and region.strip() else "غير محدد"
        prompt = (
            "حلل هذا الحدث الجيوسياسي من منظور الأمن الوطني السعودي: "
            f"'{desc}'. المنطقة: {region_value}. "
            "قدّم: 1) تقدير التأثير 2) احتمال التصعيد بالنسبة المئوية "
            "3) تعديل الوضع الموصى به 4) آثار من الدرجة الثانية 5) آثار من الدرجة الثالثة "
            "6) مؤشرات يجب مراقبتها. التصنيف: UNCLASSIFIED - FOUO."
        )
        raw = self._ask_llm(prompt, TaskDomain.ARABIC_NLP if contains_arabic(desc) else TaskDomain.REASONING)
        if not raw or "pending - engine not yet loaded" in raw.lower():
            result = self._fallback(desc, region)
            self.history.append(result)
            return result
        result = {
            "event": desc,
            "region": region,
            "impact": self._parse_impact(raw),
            "escalation_likelihood_pct": self._parse_percentage(raw),
            "recommended_posture": "مواصلة التقييم المرحلي للموقف." if "توصية" not in raw else raw.splitlines()[0],
            "second_order_effects": as_list(self._parse_list(raw, "الثانية")),
            "third_order_effects": as_list(self._parse_list(raw, "الثالثة")),
            "indicators_to_watch": as_list(self._parse_list(raw, "مؤشرات")),
            "raw_analysis": raw,
            "timestamp": utc_now_iso(),
        }
        self.history.append(result)
        return result

    def batch_analyze(self, events: List[str]) -> List[dict]:
        if not isinstance(events, list):
            raise ValueError("events must be a list of strings")
        return [self.analyze(event) for event in events if isinstance(event, str) and event.strip()]

