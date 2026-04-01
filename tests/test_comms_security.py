"""Unit tests for comms security manager."""

from __future__ import annotations

from datetime import datetime, timezone

from services.comms.c2.comms_security import CommsSecurityManager
from services.comms.models import Message, MessagePriority, MessageStatus, MessageType


def _message(body: str = "Secure payload") -> Message:
    return Message(
        message_id="msg-sec",
        timestamp=datetime.now(timezone.utc),
        sender_id="node-1",
        sender_callsign="COMMAND-ALPHA",
        recipient_ids=["node-2"],
        channel_id="chan-1",
        message_type=MessageType.ORDER,
        priority=MessagePriority.PRIORITY,
        status=MessageStatus.QUEUED,
        subject="SEC",
        body=body,
        language="en",
        relay_backend="simulated",
        encryption_protocol="none",
    )


def test_encrypt_decrypt_roundtrip_preserves_body():
    manager = CommsSecurityManager()
    message = _message("Top tactical detail")
    encrypted = manager.encrypt_message(message, protocol="aes256")
    assert encrypted.body != "Top tactical detail"
    decrypted = manager.decrypt_message(encrypted)
    assert decrypted.body == "Top tactical detail"


def test_validate_classification_passes_valid():
    manager = CommsSecurityManager()
    message = _message()
    message.classification = "UNCLASSIFIED - FOUO"
    assert manager.validate_classification(message) is True


def test_sanitize_for_logging_strips_body():
    manager = CommsSecurityManager()
    message = _message("Sensitive body")
    sanitized = manager.sanitize_for_logging(message)
    assert "body" not in sanitized
    assert sanitized["body_redacted"] is True


def test_key_exchange_generates_key_for_node():
    manager = CommsSecurityManager()
    result = manager.key_exchange("node-77")
    assert result["node_id"] == "node-77"
    registry = manager.get_key_registry()
    assert any(entry["node_id"] == "node-77" for entry in registry)
