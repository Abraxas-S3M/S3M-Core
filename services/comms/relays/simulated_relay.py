"""Simulated relay backend for offline tactical communications testing."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from services.comms.models import (
    Channel,
    ChannelType,
    Message,
    MessageStatus,
    MessagePriority,
    RelayStatus,
)


class SimulatedRelay:
    """Zero-dependency relay emulating encrypted message transport for drills."""

    def __init__(self) -> None:
        self.connected = False
        self.message_queue: Dict[str, List[Message]] = {}
        self.channels: Dict[str, Channel] = {}

    def connect(self) -> bool:
        self.connected = True
        return True

    def send(self, message: Message) -> bool:
        channel_id = message.channel_id or "direct"
        if channel_id not in self.message_queue:
            self.message_queue[channel_id] = []
        message.status = MessageStatus.SENDING
        self.message_queue[channel_id].append(message)
        # Tactical simulation delay for transport/relay processing.
        time.sleep(0.05)
        message.status = MessageStatus.DELIVERED
        return True

    def receive(
        self,
        channel_id: Optional[str],
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Message]:
        if channel_id:
            messages = list(self.message_queue.get(channel_id, []))
        else:
            messages = []
            for queued in self.message_queue.values():
                messages.extend(queued)
        if since is not None:
            messages = [msg for msg in messages if msg.timestamp > since]
        return sorted(messages, key=lambda m: m.timestamp)[-limit:]

    def create_channel(
        self,
        name: str,
        channel_type: ChannelType,
        members: List[str],
    ) -> Channel:
        channel = Channel(
            channel_id=f"sim-{uuid4().hex[:10]}",
            name=name,
            channel_type=channel_type,
            members=list(members),
            relay_backend="simulated",
            encryption_required=True,
            priority_default=MessagePriority.ROUTINE,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.channels[channel.channel_id] = channel
        self.message_queue.setdefault(channel.channel_id, [])
        return channel

    def list_channels(self) -> List[Channel]:
        return list(self.channels.values())

    def get_status(self) -> RelayStatus:
        return RelayStatus.ONLINE

    def broadcast(self, message: Message, channels: List[str]) -> Dict[str, bool]:
        results: Dict[str, bool] = {}
        for channel_id in channels:
            clone = Message.from_dict(message.to_dict())
            clone.channel_id = channel_id
            results[channel_id] = self.send(clone)
        return results
