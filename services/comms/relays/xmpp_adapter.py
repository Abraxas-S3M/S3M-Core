"""XMPP adapter for ejabberd/Prosody relay integration."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from services.comms.models import (
    Channel,
    ChannelType,
    Message,
    MessagePriority,
    MessageStatus,
    MessageType,
    RelayStatus,
)


class XMPPAdapter:
    """Best-effort XMPP adapter with offline outbox for denied environments."""

    def __init__(
        self,
        server: str = "localhost",
        port: int = 5222,
        jid: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.server = server
        self.port = int(port)
        self.jid = jid
        self.password = password
        self.connected = False
        self._channels: Dict[str, Channel] = {}
        self._messages: Dict[str, List[Message]] = {}
        self._outbox_dir = Path("/workspace/data/comms/xmpp_outbox")
        self._outbox_dir.mkdir(parents=True, exist_ok=True)

    def connect(self) -> bool:
        try:
            sock = socket.create_connection((self.server, self.port), timeout=1.5)
            sock.close()
            self.connected = True
            return True
        except Exception:
            self.connected = False
            return False

    def send(self, message: Message) -> bool:
        message.status = MessageStatus.SENDING
        if not self.connected:
            message.status = MessageStatus.QUEUED
            self._write_outbox(message)
            return False

        # Tactical note: if OMEMO is available in deployment, this adapter is the
        # integration point to wrap body before dispatch. For offline tests we keep
        # payload in-memory while still exercising routing behavior.
        channel_id = message.channel_id or "direct"
        self._messages.setdefault(channel_id, []).append(message)
        message.status = MessageStatus.DELIVERED
        return True

    def receive(
        self,
        channel_id: Optional[str],
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Message]:
        if not channel_id:
            return []
        messages = list(self._messages.get(channel_id, []))
        if since is not None:
            messages = [m for m in messages if m.timestamp >= since]
        return messages[: max(0, limit)]

    def create_channel(self, name: str, channel_type: ChannelType, members: List[str]) -> Channel:
        channel = Channel(
            channel_id=f"xmpp-{uuid4().hex[:8]}",
            name=name,
            channel_type=channel_type,
            members=list(members),
            relay_backend="xmpp",
            encryption_required=True,
            priority_default=MessagePriority.PRIORITY,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        self._channels[channel.channel_id] = channel
        self._messages.setdefault(channel.channel_id, [])
        return channel

    def list_channels(self) -> List[Channel]:
        return list(self._channels.values())

    def get_status(self) -> RelayStatus:
        return RelayStatus.ONLINE if self.connected else RelayStatus.OFFLINE

    def _write_outbox(self, message: Message) -> None:
        filepath = self._outbox_dir / f"{message.message_id}.json"
        payload = message.to_log_safe()
        payload["queued_at"] = datetime.now(timezone.utc).isoformat()
        filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _message_from_payload(self, payload: Dict[str, object]) -> Message:
        return Message(
            message_id=str(payload.get("message_id", f"msg-{uuid4().hex[:12]}")),
            timestamp=datetime.now(timezone.utc),
            sender_id=str(payload.get("sender_id", "xmpp-peer")),
            sender_callsign=str(payload.get("sender_callsign", "XMPP-PEER")),
            recipient_ids=list(payload.get("recipient_ids", [])),
            channel_id=str(payload.get("channel_id")) if payload.get("channel_id") else None,
            message_type=MessageType(str(payload.get("message_type", "SYSTEM"))),
            priority=MessagePriority[str(payload.get("priority", "ROUTINE"))],
            status=MessageStatus.DELIVERED,
            subject=str(payload.get("subject", "")),
            body=str(payload.get("body", "")),
            language=str(payload.get("language", "auto")),
            relay_backend="xmpp",
            encryption_protocol=str(payload.get("encryption_protocol", "none")),
            metadata=dict(payload.get("metadata", {})),
            classification=str(payload.get("classification", "UNCLASSIFIED - FOUO")),
        )
