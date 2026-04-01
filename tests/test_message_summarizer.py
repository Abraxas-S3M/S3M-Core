from __future__ import annotations

from datetime import datetime, timezone

from services.comms.models import Message, MessagePriority, MessageStatus, MessageType
from services.comms.nlp import ArabicNLPEngine, MessageSummarizer


def _message(mid: str, body: str) -> Message:
    return Message(
        message_id=mid,
        timestamp=datetime.now(timezone.utc),
        sender_id="node-1",
        sender_callsign="EAGLE-01",
        recipient_ids=["node-2"],
        channel_id="chan-1",
        message_type=MessageType.REPORT,
        priority=MessagePriority.PRIORITY,
        status=MessageStatus.QUEUED,
        subject="Report",
        body=body,
        language="auto",
        relay_backend="simulated",
        encryption_protocol="none",
    )


def test_summarize_message_enriches_message():
    summarizer = MessageSummarizer(engine=ArabicNLPEngine(model_backend="keyword"))
    message = _message("m1", "request support from EAGLE-01 near 5000, 3000")
    enriched = summarizer.summarize_message(message)
    assert enriched.summary is not None
    assert isinstance(enriched.extracted_entities, list)
    assert enriched.extracted_intent == "request_support"


def test_summarize_channel_traffic_returns_expected_keys():
    summarizer = MessageSummarizer(engine=ArabicNLPEngine(model_backend="keyword"))
    messages = [_message("m1", "intel update enemy at 5000, 3000")]
    data = summarizer.summarize_channel_traffic(messages, time_window_minutes=60)
    assert "situation" in data
    assert "key_entities" in data
    assert "outstanding_requests" in data
    assert "recommended_actions" in data


def test_generate_comms_brief_returns_non_empty():
    summarizer = MessageSummarizer(engine=ArabicNLPEngine(model_backend="keyword"))
    channels = [{"channel_id": "chan-1", "name": "COMMAND"}]
    messages = [_message("m1", "routine check")]
    brief = summarizer.generate_comms_brief(channels, messages)
    assert isinstance(brief, str)
    assert brief.strip()
