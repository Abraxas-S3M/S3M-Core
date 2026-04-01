"""Matrix/Synapse relay adapter for secure C2 message exchange."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request
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

LOGGER = logging.getLogger(__name__)


class MatrixAdapter:
    """Lightweight Matrix adapter using stdlib urllib only."""

    def __init__(self, homeserver_url: str = "http://localhost:8008", access_token: Optional[str] = None) -> None:
        self.homeserver_url = homeserver_url.rstrip("/")
        self.access_token = access_token
        self.connected = False
        self.channels: Dict[str, Channel] = {}
        self._status = RelayStatus.OFFLINE
        self._outbox = Path("/workspace/data/comms/matrix_outbox")
        self._outbox.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def connect(self) -> bool:
        url = f"{self.homeserver_url}/_matrix/client/versions"
        req = request.Request(url, method="GET")
        try:
            with request.urlopen(req, timeout=1.0) as resp:
                if 200 <= resp.status < 300:
                    self.connected = True
                    self._status = RelayStatus.ONLINE
                    return True
        except Exception as exc:
            LOGGER.info("Matrix adapter offline: %s", exc)
        self.connected = False
        self._status = RelayStatus.OFFLINE
        return False

    def _queue_outbox(self, message: Message, reason: str) -> None:
        payload = {
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "message": message.to_log_safe(),
        }
        target = self._outbox / f"{message.message_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def send(self, message: Message) -> bool:
        if not self.connected:
            self._queue_outbox(message, "matrix_offline")
            return False
        room_id = message.channel_id or "!default:localhost"
        tx_id = uuid4().hex[:16]
        endpoint = f"{self.homeserver_url}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{tx_id}"
        event = {
            "msgtype": "m.text",
            "body": message.body,
            "s3m": {
                "message_id": message.message_id,
                "sender_callsign": message.sender_callsign,
                "priority": message.priority.name,
                "message_type": message.message_type.value,
                "classification": message.classification,
            },
        }
        req = request.Request(
            endpoint,
            method="POST",
            headers=self._headers(),
            data=json.dumps(event).encode("utf-8"),
        )
        try:
            with request.urlopen(req, timeout=1.5) as resp:
                if 200 <= resp.status < 300:
                    message.status = MessageStatus.DELIVERED
                    return True
        except error.URLError:
            self._queue_outbox(message, "matrix_send_error")
        return False

    def receive(self, channel_id: Optional[str], since: Optional[datetime] = None, limit: int = 50) -> List[Message]:
        if not self.connected:
            return []
        if not channel_id:
            return []
        endpoint = f"{self.homeserver_url}/_matrix/client/v3/rooms/{channel_id}/messages?dir=b&limit={limit}"
        req = request.Request(endpoint, method="GET", headers=self._headers())
        out: List[Message] = []
        try:
            with request.urlopen(req, timeout=1.5) as resp:
                if not (200 <= resp.status < 300):
                    return out
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return out

        for event in payload.get("chunk", []):
            origin_ts = event.get("origin_server_ts", 0)
            ts = datetime.fromtimestamp(origin_ts / 1000.0, tz=timezone.utc) if origin_ts else datetime.now(timezone.utc)
            if since and ts <= since:
                continue
            content = event.get("content", {})
            meta = content.get("s3m", {})
            out.append(
                Message(
                    message_id=meta.get("message_id", f"mx-{uuid4().hex[:10]}"),
                    timestamp=ts,
                    sender_id=event.get("sender", "matrix"),
                    sender_callsign=meta.get("sender_callsign", event.get("sender", "MATRIX")),
                    recipient_ids=[],
                    channel_id=channel_id,
                    message_type=MessageType(meta.get("message_type", "REPORT")),
                    priority=MessagePriority[meta.get("priority", "ROUTINE")],
                    status=MessageStatus.DELIVERED,
                    subject="",
                    body=str(content.get("body", "")),
                    language="auto",
                    relay_backend="matrix",
                    encryption_protocol="matrix_olm",
                    metadata={"matrix_event_id": event.get("event_id")},
                    classification=meta.get("classification", "UNCLASSIFIED - FOUO"),
                )
            )
        return out

    def create_channel(self, name: str, channel_type: ChannelType, members: List[str]) -> Channel:
        # Tactical context: command channels are restricted and encrypted by default.
        channel = Channel(
            channel_id=f"!{name.lower().replace(' ', '_')}_{uuid4().hex[:8]}:localhost",
            name=name,
            channel_type=channel_type,
            members=list(members),
            relay_backend="matrix",
            encryption_required=True,
            priority_default=MessagePriority.PRIORITY if channel_type == ChannelType.COMMAND_NET else MessagePriority.ROUTINE,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.channels[channel.channel_id] = channel
        return channel

    def join_channel(self, channel_id: str) -> bool:
        return channel_id in self.channels or self.connected

    def list_channels(self) -> List[Channel]:
        return list(self.channels.values())

    def get_status(self) -> RelayStatus:
        return RelayStatus.ONLINE if self.connected else self._status
