"""Intent classification for commander natural-language requests.

Military context:
Deterministic intent parsing ensures critical command intents are routed quickly
even when LLM acceleration is unavailable in disconnected conditions.
"""

from __future__ import annotations

import re
from typing import Dict

from services.command_agent.models import CommandContext, CommandIntent


class IntentClassifier:
    """Keyword-first intent classifier with confidence scoring."""

    def __init__(self):
        self.intent_keywords = {
            CommandIntent.MOVE_UNIT: ["send", "move", "deploy", "return", "عودة", "أرسل", "انقل", "القاعدة"],
            CommandIntent.ENGAGE_TARGET: ["engage", "attack", "fire", "هاجم", "اشتبك"],
            CommandIntent.AUTHORIZE_KILLCHAIN: ["authorize", "approve", "kill chain", "صرح", "وافق"],
            CommandIntent.SET_ROE: ["set roe", "rules of engagement", "قواعد الاشتباك"],
            CommandIntent.QUERY_THREATS: ["threat", "threats", "تهديد", "تهديدات"],
            CommandIntent.QUERY_READINESS: ["readiness", "manning", "جاهزية", "قوام"],
            CommandIntent.QUERY_STATUS: ["status", "حالة"],
            CommandIntent.ANALYZE_RISK: ["risk", "assess", "مخاطر", "تقييم"],
            CommandIntent.GENERATE_REPORT: ["report", "sitrep", "intsum", "opord", "تقرير", "إنشاء"],
            CommandIntent.GENERATE_BRIEF: ["brief", "briefing", "إحاطة"],
        }

    def classify(self, text: str, context: CommandContext) -> tuple[CommandIntent, float]:
        """Classify command intent with deterministic keyword scoring."""
        norm = (text or "").lower()
        if not norm.strip():
            return CommandIntent.UNKNOWN, 0.0

        best_intent = CommandIntent.UNKNOWN
        best_score = 0
        for intent, keywords in self.intent_keywords.items():
            score = sum(1 for k in keywords if k in norm)
            if score > best_score:
                best_score = score
                best_intent = intent

        if best_intent == CommandIntent.UNKNOWN:
            return best_intent, 0.2

        confidence = min(0.95, 0.55 + (best_score * 0.15))
        if confidence < 0.7:
            # Offline fallback for ambiguous commands.
            if "upload" in norm or "pdf" in norm:
                return CommandIntent.UPLOAD_DOCUMENT, 0.75
            if "csv" in norm or "excel" in norm or "spreadsheet" in norm:
                return CommandIntent.UPLOAD_DATA, 0.75
            if "image" in norm or "photo" in norm:
                return CommandIntent.UPLOAD_IMAGE, 0.75
        return best_intent, confidence

    def extract_entities(self, text: str, intent: CommandIntent) -> dict:
        """Extract tactical entities (units, grids, targets, weapons, params)."""
        units = re.findall(r"\b[A-Z]{1,4}-\d+\b", text)
        locations = re.findall(r"\b\d{3,6}\s*,\s*\d{3,6}\b", text)
        targets = re.findall(r"\b(hostile\s+\w+|enemy\s+\w+|uav|tank|radar)\b", text.lower())
        weapons = re.findall(r"\b(missile|rocket|gun|torpedo|munition)\b", text.lower())

        params: Dict[str, str] = {}
        roe_match = re.search(r"(weapons_free|weapons_tight|weapons_hold)", text.lower())
        if roe_match:
            params["roe_level"] = roe_match.group(1)
        level_match = re.search(r"level\s*(\d)", text.lower())
        if level_match:
            params["authority_level"] = level_match.group(1)

        return {
            "units": units,
            "locations": locations,
            "targets": targets,
            "weapons": weapons,
            "parameters": params,
        }
