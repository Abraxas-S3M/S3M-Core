"""Arabic/English NLP processing engine for tactical message summarization."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.comms.models import Message, MessagePriority, MessageSummary

try:
    from src.llm_core import Orchestrator, QueryRequest, TaskDomain
except Exception:  # pragma: no cover - optional integration fallback
    Orchestrator = None  # type: ignore
    QueryRequest = None  # type: ignore
    TaskDomain = None  # type: ignore


class ArabicNLPEngine:
    """Central NLP processor with strict offline fallback chain."""

    def __init__(self, model_backend: str = "auto") -> None:
        self.requested_backend = model_backend
        self.backend = self._select_backend(model_backend)
        self._orchestrator = Orchestrator() if Orchestrator is not None else None
        self._keywords_backend = "keyword_fallback"
        self._arabic_places = {
            "الرياض",
            "جدة",
            "الدمام",
            "المدينة",
            "مكة",
            "تبوك",
            "القصيم",
            "الخبر",
            "نجران",
            "الجبيل",
            "الدوحة",
            "أبوظبي",
            "دبي",
            "المنامة",
            "الكويت",
            "مسقط",
        }

    def _select_backend(self, model_backend: str) -> str:
        if model_backend not in {"auto", "arabert", "mt5", "transformers", "allam", "keyword"}:
            return "keyword"
        if model_backend == "keyword":
            return "keyword"
        if model_backend == "allam":
            return "allam"
        if model_backend == "arabert" or (
            model_backend == "auto" and os.path.isdir("models/arabic/arabert/")
        ):
            return "arabert_local"
        if model_backend == "mt5" or (
            model_backend == "auto" and os.path.isdir("models/arabic/mt5/")
        ):
            return "mt5_local"
        if model_backend in {"auto", "transformers"}:
            try:
                import transformers  # type: ignore # pragma: no cover - optional

                _ = transformers
                return "transformers"
            except Exception:
                pass
        if model_backend in {"auto", "allam"}:
            return "allam"
        return "keyword"

    @staticmethod
    def _contains_arabic(text: str) -> bool:
        return any(0x0600 <= ord(ch) <= 0x06FF for ch in text)

    def _detect_language(self, text: str, requested: str) -> str:
        if requested in {"en", "ar"}:
            return requested
        return "ar" if self._contains_arabic(text) else "en"

    def _llm_summarize(self, prompt: str, domain: Optional[Any]) -> Optional[str]:
        if self._orchestrator is None or QueryRequest is None:
            return None
        try:
            req = QueryRequest(prompt=prompt, domain=domain)
            result = self._orchestrator.process(req)
            return str(getattr(result, "text", "")).strip() or None
        except Exception:
            return None

    def _summarize_with_backend(self, text: str, language: str, max_length: int) -> tuple[str, str]:
        if language == "ar":
            if self.backend in {"arabert_local", "mt5_local", "transformers"}:
                short = re.sub(r"\s+", " ", text).strip()[: max_length * 2]
                return (f"ملخص تكتيكي: {short[:max_length]}", self.backend)
            if self.backend == "allam":
                answer = self._llm_summarize(
                    prompt=f"لخص هذا النص العسكري في جملتين: {text}",
                    domain=TaskDomain.ARABIC_NLP if TaskDomain is not None else None,
                )
                if answer:
                    return (answer[: max_length * 4], "allam")
        else:
            answer = self._llm_summarize(
                prompt=f"Summarize this military message in 2 sentences: {text}",
                domain=TaskDomain.TACTICAL if TaskDomain is not None else None,
            )
            if answer:
                return (answer[: max_length * 4], "phi3_orchestrator")

        fallback = re.sub(r"\s+", " ", text).strip()[:max_length]
        return (fallback, self._keywords_backend)

    def summarize(
        self,
        text: str,
        language: str = "auto",
        max_length: int = 100,
        message_id: Optional[str] = None,
        priority: Optional[MessagePriority] = None,
    ) -> MessageSummary:
        start = time.time()
        original_language = self._detect_language(text, language)
        summary_text, backend_used = self._summarize_with_backend(text=text, language=original_language, max_length=max_length)
        entities = self.extract_entities(text)
        intent = self.classify_intent(text)
        urgency = self.score_urgency(text=text, priority=priority)
        sentiment = "distress" if urgency >= 0.9 else ("urgent" if urgency >= 0.6 else "routine")

        summary_ar: Optional[str] = summary_text if original_language == "ar" else None
        summary_en: Optional[str] = summary_text if original_language == "en" else None

        if original_language == "ar":
            en_fallback = self._llm_summarize(
                prompt=f"Translate and summarize this Arabic military message in English: {text}",
                domain=TaskDomain.TACTICAL if TaskDomain is not None else None,
            )
            if en_fallback:
                summary_en = en_fallback[: max_length * 4]
        elif original_language == "en":
            ar_fallback = self._llm_summarize(
                prompt=f"لخص الرسالة العسكرية التالية بالعربية: {text}",
                domain=TaskDomain.ARABIC_NLP if TaskDomain is not None else None,
            )
            if ar_fallback:
                summary_ar = ar_fallback[: max_length * 4]

        return MessageSummary(
            message_id=message_id or f"summary-{uuid4().hex[:10]}",
            original_language=original_language,
            summary_ar=summary_ar,
            summary_en=summary_en,
            entities=entities,
            intent=intent,
            urgency_score=urgency,
            sentiment=sentiment,
            model_used=backend_used,
            processing_time_ms=(time.time() - start) * 1000.0,
        )

    def summarize_batch(self, messages: List[Message]) -> List[MessageSummary]:
        summaries: List[MessageSummary] = []
        for message in messages:
            summary = self.summarize(message.body, language=message.language)
            summary.message_id = message.message_id
            summaries.append(summary)
        return summaries

    def extract_entities(self, text: str) -> List[dict]:
        patterns = [
            ("location", re.compile(r"\b\d{4,6}\s*,\s*\d{4,6}\b"), 0.88),
            ("unit", re.compile(r"\b[A-Z]+-[A-Z0-9]+\b"), 0.92),
            ("threat", re.compile(r"\b(enemy|hostile|IED|ambush)\b|عدو|معادي|كمين", re.IGNORECASE), 0.94),
            ("time", re.compile(r"\b\d{4}\b|at dawn|في الفجر|قبل الغروب", re.IGNORECASE), 0.82),
            (
                "unit",
                re.compile(r"\b\d+(st|nd|rd|th)\s+Battalion\b|الكتيبة\s+الأولى|الكتيبة\s+الثانية", re.IGNORECASE),
                0.86,
            ),
        ]
        entities: List[dict] = []
        for entity_type, pattern, confidence in patterns:
            for match in pattern.finditer(text):
                entities.append(
                    {
                        "type": entity_type,
                        "value": match.group(0),
                        "confidence": confidence,
                        "position": match.start(),
                    }
                )
        for place in self._arabic_places:
            pos = text.find(place)
            if pos >= 0:
                entities.append({"type": "location", "value": place, "confidence": 0.9, "position": pos})
        return entities

    def classify_intent(self, text: str) -> str:
        lookup = {
            "request_support": ["request support", "نحتاج دعم", "طلب دعم"],
            "report_contact": ["enemy contact", "تقرير اشتباك", "اشتباك"],
            "order_movement": ["move to", "تقدم إلى", "تحرك إلى"],
            "intel_update": ["intel update", "تقرير موقف", "تحديث استخباراتي"],
            "medical_emergency": ["medical", "إصابة", "إخلاء طبي"],
            "order_withdrawal": ["withdraw", "انسحاب", "تراجع"],
        }
        lowered = text.lower()
        for intent, phrases in lookup.items():
            for phrase in phrases:
                if phrase.lower() in lowered:
                    return intent

        if self._orchestrator and QueryRequest:
            prompt = (
                "Classify this tactical message intent as one of: "
                "request_support, report_contact, order_movement, intel_update, medical_emergency, order_withdrawal. "
                f"Message: {text}"
            )
            llm_answer = self._llm_summarize(prompt, TaskDomain.REASONING if TaskDomain is not None else None)
            if llm_answer:
                normalized = llm_answer.strip().split()[0].strip(".,:;").lower()
                if normalized in lookup:
                    return normalized
        return "intel_update"

    def score_urgency(self, text: str, priority: Optional[MessagePriority] = None) -> float:
        weights = {
            MessagePriority.FLASH: 1.0,
            MessagePriority.IMMEDIATE: 0.8,
            MessagePriority.PRIORITY: 0.6,
            MessagePriority.ROUTINE: 0.3,
            MessagePriority.DEFERRED: 0.1,
        }
        base = weights.get(priority, 0.4)
        lowered = text.lower()
        boosters = ["immediate", "emergency", "urgent", "فوري", "طوارئ", "عاجل"]
        if any(token in lowered for token in boosters):
            base += 0.2
        base += min(0.1, text.count("!") * 0.05)
        return max(0.0, min(1.0, base))

    def get_model_info(self) -> dict:
        return {
            "requested_backend": self.requested_backend,
            "active_backend": self.backend,
            "orchestrator_available": self._orchestrator is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def health_check(self) -> dict:
        info = self.get_model_info()
        info["status"] = "operational"
        return info


class EntityExtractor:
    """Convenience extractor wrapper for modular NLP pipelines."""

    def __init__(self, engine: Optional[ArabicNLPEngine] = None) -> None:
        self.engine = engine or ArabicNLPEngine()

    def extract(self, text: str) -> List[dict]:
        return self.engine.extract_entities(text)


class IntentClassifier:
    """Convenience classifier wrapper for modular NLP pipelines."""

    def __init__(self, engine: Optional[ArabicNLPEngine] = None) -> None:
        self.engine = engine or ArabicNLPEngine()

    def classify(self, text: str) -> str:
        return self.engine.classify_intent(text)


class UrgencyScorer:
    """Convenience urgency scorer wrapper for modular NLP pipelines."""

    def __init__(self, engine: Optional[ArabicNLPEngine] = None) -> None:
        self.engine = engine or ArabicNLPEngine()

    def score(self, text: str, priority: Optional[MessagePriority] = None) -> float:
        return self.engine.score_urgency(text=text, priority=priority)
