"""Rocket.Chat adapter with local offline outbox fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib import request
from uuid import uuid4

from services.comms.models import Channel, ChannelType, Message, MessagePriority, MessageStatus, RelayStatus

LOGGER = logging.getLogger(__name__)


class RocketChatAdapter:
    """Rocket.Chat backend adapter for tactical base-network deployment."""

    def __init__(self, url: str = "http://localhost:3000", username: Optional[str] = None, password: Optional[str] = None):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self._connected = False
        self._channels: Dict[str, Channel] = {}
        self._messages: Dict[str, List[Message]] = {}
        self._outbox_dir = Path("data/comms/rocketchat_outbox")
        self._outbox_dir.mkdir(parents=True, exist_ok=True)

    def _offline_queue(self, message: Message) -> None:
        payload = message.to_dict()
        payload["body"] = "[REDACTED]"
        path = self._outbox_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{message.message_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def connect(self) -> bool:
        try:
            req = request.Request(
                f"{self.url}/api/v1/info",
                method="GET",
            )
            with request.urlopen(req, timeout=2.0) as resp:
                self._connected = 200 <= getattr(resp, "status", 500) < 300
        except Exception as exc:
            self._connected = False
            LOGGER.info("Rocket.Chat unavailable; adapter offline: %s", exc)
        return self._connected

    def send(self, message: Message) -> bool:
        message.status = MessageStatus.SENDING
        channel_id = message.channel_id or "general"
        if not self._connected:
            message.status = MessageStatus.QUEUED
            self._offline_queue(message)
            return False

        body = {
            "channel": channel_id,
            "text": message.body,
        }
        data = json.dumps(body).encode("utf-8")
        try:
            req = request.Request(
                f"{self.url}/api/v1/chat.sendMessage",
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with request.urlopen(req, timeout=2.0) as resp:
                if 200 <= getattr(resp, "status", 500) < 300:
                    message.status = MessageStatus.DELIVERED
                    self._messages.setdefault(channel_id, []).append(message)
                    return True
        except Exception:
            pass
        message.status = MessageStatus.QUEUED
        self._offline_queue(message)
        return False

    def receive(self, channel_id: Optional[str], since: Optional[datetime] = None, limit: int = 50) -> List[Message]:
        # Tactical fallback path for air-gapped test mode.
        if not channel_id:
            return []
        messages = list(self._messages.get(channel_id, []))
        if since is not None:
            messages = [m for m in messages if m.timestamp >= since]
        return messages[-max(1, int(limit)) :]

    def create_channel(self, name: str, channel_type: ChannelType, members: List[str]) -> Channel:
        channel_id = f"rc-{uuid4().hex[:10]}"
        channel = Channel(
            channel_id=channel_id,
            name=name,
            channel_type=channel_type,
            members=list(members),
            relay_backend="rocket_chat",
            encryption_required=True,
            priority_default=MessagePriority.ROUTINE,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        self._channels[channel_id] = channel
        self._messages.setdefault(channel_id, [])
        if self._connected:
            payload = json.dumps({"name": name}).encode("utf-8")
            try:
                req = request.Request(
                    f"{self.url}/api/v1/channels.create",
                    data=payload,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with request.urlopen(req, timeout=2.0):
                    pass
            except Exception:
                pass
        return channel

    def list_channels(self) -> List[Channel]:
        return list(self._channels.values())

    def get_status(self) -> RelayStatus:
        return RelayStatus.ONLINE if self._connected else RelayStatus.OFFLINE
