"""Offline OSINT analysis pipeline with bilingual intelligence enrichment."""

from __future__ import annotations

import importlib
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from src.apps._shared import contains_arabic
from src.apps.intel.models import OSINTItem
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class OSINTAnalyzer:
    """Analyze OSINT content for intelligence-grade fusion workflows."""

    def __init__(self, nlp_engine=None):
        self.orchestrator = Orchestrator()
        self.nlp_engine = nlp_engine or self._try_load_phase14_engine()
        self.known_facts = {
            "locations": {
                "bab el-mandeb",
                "strait of hormuz",
                "red sea",
                "persian gulf",
                "riyadh",
                "jeddah",
                "yemen",
                "iran",
                "gulf of aden",
            },
            "weapons": {"sa-22", "shahed-136", "patriot", "sam", "uav", "drone"},
        }

    def _try_load_phase14_engine(self):
        # Tactical context: Phase 19 must inherit Arabic NLP capability from previous layers.
        candidates = (
            "services.comms.nlp.arabic_nlp",
            "services.comms.nlp.engine",
            "src.services.comms.nlp.arabic_nlp",
            "src.services.comms.nlp.engine",
        )
        for module_name in candidates:
            try:
                module = importlib.import_module(module_name)
                engine_cls = getattr(module, "ArabicNLPEngine", None)
                if engine_cls:
                    return engine_cls()
            except Exception:
                continue
        return None

    def _detect_language(self, text: str) -> str:
        if contains_arabic(text):
            return "ar"
        return "en"

    def _extract_people_orgs_locations(self, text: str) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []

        patterns = {
            "military_unit": [
                r"\b\d+(?:st|nd|rd|th)\s+Marine Division\b",
                r"\b\d+(?:st|nd|rd|th)\s+Armored Brigade\b",
                r"\bالفرقة\s+\w+\b",
            ],
            "weapon_system": [
                r"\bSA-22\b",
                r"\bShahed-136\b",
                r"\bPatriot\b",
                r"\bSAM\b",
                r"\bUAV\b",
                r"\bdrone\b",
            ],
            "geo_feature": [
                r"\bBab el-Mandeb\b",
                r"\bStrait of Hormuz\b",
                r"\bRed Sea\b",
                r"\bPersian Gulf\b",
                r"\bGulf of Aden\b",
                r"\bباب المندب\b",
                r"\bمضيق هرمز\b",
            ],
            "temporal_reference": [
                r"\bnext week\b",
                r"\bwithin 24 hours\b",
                r"\bالأسبوع القادم\b",
                r"\bخلال 24 ساعة\b",
            ],
            "leader": [
                r"\bPresident\s+[A-Z][a-z]+\b",
                r"\bPrime Minister\s+[A-Z][a-z]+\b",
                r"\bولي العهد\b",
            ],
        }
        for label, regexes in patterns.items():
            for rx in regexes:
                for match in re.findall(rx, text, flags=re.IGNORECASE):
                    entities.append({"type": label, "value": match})
        # Basic capitalized phrase extraction for people/org placeholders.
        for token in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text):
            if len(token.split()) >= 2:
                entities.append({"type": "possible_entity", "value": token})

        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for ent in entities:
            key = (str(ent["type"]), str(ent["value"]).lower())
            dedup[key] = ent
        return list(dedup.values())

    def _sentiment(self, text: str) -> str:
        lower = text.lower()
        alarming = [
            "attack",
            "strike",
            "missile",
            "raid",
            "drone launch",
            "sam deployment",
            "هجوم",
            "ضربة",
            "صاروخ",
            "تصعيد",
        ]
        negative = ["threat", "tension", "incursion", "warning", "تهديد", "توتر"]
        positive = ["peace", "agreement", "de-escalation", "ceasefire", "سلام", "اتفاق"]

        if any(k in lower for k in alarming):
            return "alarming"
        if any(k in lower for k in negative):
            return "negative"
        if any(k in lower for k in positive):
            return "positive"
        return "neutral"

    def _classify_topics(self, text: str) -> list[str]:
        lower = text.lower()
        map_rules = {
            "maritime_security": ["maritime", "vessel", "ship", "ais", "red sea", "hormuz", "باب المندب"],
            "cyber_operations": ["cyber", "apt", "malware", "network", "اختراق"],
            "terrorism": ["terror", "militia", "extremist", "إرهاب"],
            "diplomacy": ["summit", "diplomatic", "talks", "محادثات", "قمة"],
            "energy_security": ["oil", "pipeline", "refinery", "طاقة", "نفط"],
            "drone_threats": ["drone", "uav", "shahed", "مسيرة"],
            "border_security": ["border", "incursion", "حدود"],
            "proxy_warfare": ["proxy", "iran-backed", "وكيل"],
            "regional_stability": ["stability", "unrest", "protest", "استقرار"],
            "weapons_proliferation": ["sam", "ballistic", "weapon transfer", "أسلحة"],
        }
        out: list[str] = []
        for topic, keywords in map_rules.items():
            if any(term in lower for term in keywords):
                out.append(topic)
        return out or ["regional_stability"]

    def _credibility(self, item: OSINTItem) -> str:
        text = f"{item.title} {item.content}".lower()
        confidence_signals = 0
        for loc in self.known_facts["locations"]:
            if loc in text:
                confidence_signals += 1
        for weapon in self.known_facts["weapons"]:
            if weapon in text:
                confidence_signals += 1
        if confidence_signals >= 3:
            return "confirmed"
        if confidence_signals == 2:
            return "probable"
        if confidence_signals == 1:
            return "possible"
        if item.sentiment == "alarming":
            return "doubtful"
        return "improbable"

    def _summarize(self, text: str, language: str) -> str:
        if self.nlp_engine:
            # Tactical context: use Arabic NLP engine when available for sovereign bilingual output.
            for attr in ("summarize", "summarise"):
                fn = getattr(self.nlp_engine, attr, None)
                if callable(fn):
                    try:
                        return str(fn(text))
                    except Exception:
                        break
        prompt = (
            f"Summarize this intelligence content in {'Arabic' if language == 'ar' else 'English'} "
            f"with 2 concise sentences: {text[:1200]}"
        )
        try:
            domain = TaskDomain.ARABIC_NLP if language == "ar" else TaskDomain.PLANNING
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=domain))
            candidate = getattr(response, "text", "")
            if candidate and "pending" not in candidate.lower():
                return candidate[:500]
        except Exception:
            pass
        short = text.strip().replace("\n", " ")
        return short[:197] + "..." if len(short) > 200 else short

    def analyze(self, item: OSINTItem) -> OSINTItem:
        """Enrich an OSINT item with entities, sentiment, topic, credibility, and summary."""
        combined = f"{item.title}\n{item.content}"
        item.language = self._detect_language(combined)
        item.entities = self.extract_intelligence_entities(combined, language=item.language)
        item.sentiment = self._sentiment(combined)
        topics = self._classify_topics(combined)
        item.topics = sorted(set(item.topics + topics))
        item.credibility = self._credibility(item)
        summary_primary = self._summarize(combined, language=item.language)
        summary_other = self._summarize(combined, language="ar" if item.language == "en" else "en")
        item.summary = f"EN/AR: {summary_primary} || {summary_other}"
        return item

    def analyze_batch(self, items: list[OSINTItem]) -> list[OSINTItem]:
        return [self.analyze(item) for item in items]

    def extract_intelligence_entities(self, text: str, language: str = "auto") -> list[dict]:
        lang = self._detect_language(text) if language == "auto" else language
        entities = self._extract_people_orgs_locations(text)
        if lang == "ar":
            for val in re.findall(r"\b(القوات|الجيش|اللواء|الفرقة)\s+\w+\b", text):
                entities.append({"type": "military_unit", "value": val})
        return entities

    def cross_reference(self, items: list[OSINTItem]) -> list[dict]:
        """
        Correlate entities/events across multiple sources.

        Tactical context: corroboration from independent streams raises
        analyst confidence for command decisions.
        """
        entity_index: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"sources": set(), "items": set()}
        )
        for item in items:
            unique_values = {
                str(ent.get("value", "")).strip().lower()
                for ent in item.entities
                if str(ent.get("value", "")).strip()
            }
            for value in unique_values:
                entity_index[value]["sources"].add(item.source_id)
                entity_index[value]["items"].add(item.item_id)

        out: list[dict] = []
        for entity, row in entity_index.items():
            if len(row["sources"]) < 2:
                continue
            confidence = min(1.0, (len(row["sources"]) * 0.35) + (len(row["items"]) * 0.1))
            out.append(
                {
                    "entity": entity,
                    "sources": sorted(row["sources"]),
                    "items": sorted(row["items"]),
                    "confidence": round(confidence, 3),
                }
            )
        return sorted(out, key=lambda r: r["confidence"], reverse=True)

    @staticmethod
    def recent_within(items: list[OSINTItem], hours: int = 24) -> list[OSINTItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [item for item in items if item.timestamp.astimezone(timezone.utc) >= cutoff]
