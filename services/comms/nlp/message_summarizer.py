"""Higher-level summarization helpers for comms traffic analysis."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from services.comms.models import Message
from services.comms.nlp.arabic_nlp_engine import ArabicNLPEngine


class MessageSummarizer:
    """Enrich tactical comms messages and compile channel-level briefs."""

    def __init__(self, engine: Optional[ArabicNLPEngine] = None) -> None:
        self.engine = engine or ArabicNLPEngine(model_backend="auto")

    def summarize_message(self, message: Message) -> Message:
        source_text = str(message.metadata.get("_plaintext_body", message.body))
        summary = self.engine.summarize(
            text=source_text,
            language=message.language,
            message_id=message.message_id,
            priority=message.priority,
        )
        message.summary = summary.summary_ar if summary.original_language == "ar" else summary.summary_en
        if not message.summary:
            message.summary = summary.summary_en or summary.summary_ar
        message.extracted_entities = list(summary.entities)
        message.extracted_intent = summary.intent
        message.urgency_score = float(summary.urgency_score)
        return message

    def summarize_channel_traffic(self, messages: List[Message], time_window_minutes: int = 60) -> dict:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=max(1, int(time_window_minutes)))
        selected = [m for m in messages if m.timestamp >= cutoff]
        summaries = []
        intents: Dict[str, int] = {}
        entities: Dict[str, int] = {}
        for message in selected:
            if message.summary:
                summaries.append(message.summary)
            else:
                compact = self.engine.summarize(
                    str(message.metadata.get("_plaintext_body", message.body)),
                    language=message.language,
                    message_id=message.message_id,
                    priority=message.priority,
                )
                summaries.append(compact.summary_en or compact.summary_ar or message.body[:100])
            if message.extracted_intent:
                intents[message.extracted_intent] = intents.get(message.extracted_intent, 0) + 1
            for entity in message.extracted_entities:
                key = f"{entity.get('type')}:{entity.get('value')}"
                entities[key] = entities.get(key, 0) + 1

        if not summaries:
            return {
                "time_window_minutes": time_window_minutes,
                "message_count": 0,
                "situation": "No traffic in current tactical window.",
                "key_entities": [],
                "outstanding_requests": [],
                "recommended_actions": ["Maintain comms watch and continue monitoring."],
            }

        joined = " | ".join(summaries)
        # Tactical context: template fallback that mirrors Mistral brief format.
        outstanding_requests = [intent for intent, count in intents.items() if intent == "request_support" and count > 0]
        key_entities = sorted(entities.items(), key=lambda item: item[1], reverse=True)[:10]
        recommended = [
            "Prioritize support requests with urgency > 0.8.",
            "Validate reported positions against ISR overlays.",
            "Push concise update to command net every 15 minutes.",
        ]
        return {
            "time_window_minutes": time_window_minutes,
            "message_count": len(selected),
            "situation": joined[:400],
            "key_entities": [{"entity": key, "mentions": count} for key, count in key_entities],
            "outstanding_requests": outstanding_requests,
            "recommended_actions": recommended,
        }

    def generate_comms_brief(self, channels: List[dict], messages: List[Message]) -> str:
        by_channel: Dict[str, List[Message]] = {}
        for message in messages:
            key = message.channel_id or "direct"
            by_channel.setdefault(key, []).append(message)
        sections: List[str] = ["S3M COMMUNICATIONS BRIEF", f"Channels monitored: {len(channels)}"]
        for channel in channels:
            if hasattr(channel, "channel_id"):
                channel_id = str(getattr(channel, "channel_id"))
                channel_name = str(getattr(channel, "name", channel_id))
            elif isinstance(channel, dict):
                channel_id = str(channel.get("channel_id"))
                channel_name = str(channel.get("name", channel_id))
            else:
                channel_id = str(channel)
                channel_name = channel_id
            channel_messages = by_channel.get(channel_id, [])
            traffic = self.summarize_channel_traffic(channel_messages, time_window_minutes=60)
            sections.append(
                f"- {channel_name}: {traffic['message_count']} msgs | outstanding={','.join(traffic['outstanding_requests']) or 'none'}"
            )
        if len(sections) <= 2:
            sections.append("- No channel traffic available.")
        return "\n".join(sections)
