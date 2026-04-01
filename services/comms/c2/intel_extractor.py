"""Comms-derived intelligence extraction and Layer 02 threat handoff."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.comms.models import Message
from services.comms.nlp.arabic_nlp_engine import ArabicNLPEngine
from src.threat_detection.threat_manager import ThreatManager


class MessageIntelExtractor:
    """Extract threat/position/support indicators from message traffic."""

    def __init__(self, nlp_engine: Optional[ArabicNLPEngine] = None) -> None:
        self.nlp_engine = nlp_engine or ArabicNLPEngine()
        self.threat_manager = ThreatManager()

    def extract(self, message: Message) -> Dict[str, List[dict]]:
        source_body = str(message.metadata.get("_plaintext_body", message.body))
        text = f"{message.subject} {source_body}".strip()
        lowered = text.lower()
        threat_keywords = ["enemy", "عدو", "ied", "ambush", "كمين"]
        threat_indicators: List[dict] = []
        for keyword in threat_keywords:
            if keyword in lowered:
                threat_indicators.append(
                    {
                        "message_id": message.message_id,
                        "keyword": keyword,
                        "callsign": message.sender_callsign,
                        "classification": message.classification,
                    }
                )
        entities = message.extracted_entities or self.nlp_engine.extract_entities(text)
        position_reports = [e for e in entities if e.get("type") in {"location", "grid_ref"}]
        support_requests: List[dict] = []
        intent = message.extracted_intent or self.nlp_engine.classify_intent(text)
        if intent == "request_support":
            support_requests.append(
                {
                    "message_id": message.message_id,
                    "sender": message.sender_callsign,
                    "priority": message.priority.name,
                }
            )
        return {
            "threat_indicators": threat_indicators,
            "position_reports": position_reports,
            "support_requests": support_requests,
            "raw_entities": entities,
        }

    def extract_batch(self, messages: List[Message]) -> Dict[str, List[dict]]:
        aggregate = {
            "threat_indicators": [],
            "position_reports": [],
            "support_requests": [],
            "raw_entities": [],
        }
        for message in messages:
            result = self.extract(message)
            for key in aggregate:
                aggregate[key].extend(result.get(key, []))
        return aggregate

    def feed_to_threat_detection(self, indicators: List[dict]) -> List[str]:
        created_ids: List[str] = []
        for indicator in indicators:
            keyword = str(indicator.get("keyword", "threat")).upper()
            description = f"Comms-derived threat indicator detected: {keyword}"
            try:
                event = self.threat_manager.ingest_manual(
                    title=f"Comms Threat - {keyword}",
                    description=description,
                    level="HIGH",
                    category="HYBRID",
                )
                created_ids.append(event.event_id)
            except Exception:
                continue
        return created_ids
