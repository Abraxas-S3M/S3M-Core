from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from services.comms.models import Message, MessagePriority, MessageStatus, MessageType, RelayStatus
from services.comms.relays.matrix_adapter import MatrixAdapter


def _message() -> Message:
    return Message(
        message_id="mx-1",
        timestamp=datetime.now(timezone.utc),
        sender_id="node-1",
        sender_callsign="EAGLE-01",
        recipient_ids=["node-2"],
        channel_id="room-1",
        message_type=MessageType.REPORT,
        priority=MessagePriority.ROUTINE,
        status=MessageStatus.QUEUED,
        subject="test",
        body="hello",
        language="en",
        relay_backend="matrix",
        encryption_protocol="matrix_olm",
    )


def test_connect_returns_false_when_server_unreachable() -> None:
    adapter = MatrixAdapter(homeserver_url="http://127.0.0.1:9")
    assert adapter.connect() is False


def test_send_offline_saves_to_outbox(tmp_path: Path) -> None:
    adapter = MatrixAdapter(homeserver_url="http://127.0.0.1:9")
    adapter._outbox = tmp_path
    adapter._outbox.mkdir(parents=True, exist_ok=True)
    ok = adapter.send(_message())
    assert ok is False
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1


def test_get_status_offline_when_not_connected() -> None:
    adapter = MatrixAdapter(homeserver_url="http://127.0.0.1:9")
    assert adapter.get_status() == RelayStatus.OFFLINE
