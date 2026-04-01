"""Meshtastic LoRa adapter with safe offline fallback."""

from __future__ import annotations

from datetime import datetime, timezone
import queue
from typing import Dict, List, Optional

from services.comms.models import (
    Channel,
    ChannelType,
    Message,
    MessagePriority,
    MessageStatus,
    MessageType,
    RelayStatus,
)


class MeshtasticAdapter:
    """Adapter for mesh communications in denied RF/internet environments."""

    def __init__(self, serial_port: str = "/dev/ttyUSB0", tcp_host: Optional[str] = None) -> None:
        self.serial_port = serial_port
        self.tcp_host = tcp_host
        self._connected = False
        self._mesh_available = False
        self._inbox: "queue.Queue[dict]" = queue.Queue()
        self._nodes: Dict[str, dict] = {}
        self._channels: Dict[str, Channel] = {}
        self._signal = {"snr": None, "rssi": None, "hop_count": 0}

    def connect(self) -> bool:
        try:
            import meshtastic  # type: ignore # pragma: no cover - optional dependency

            _ = meshtastic
            self._mesh_available = True
            self._connected = True
        except Exception:
            self._mesh_available = False
            self._connected = False
        return self._connected

    @staticmethod
    def _priority_hop_limit(priority: MessagePriority) -> int:
        mapping = {
            MessagePriority.FLASH: 7,
            MessagePriority.IMMEDIATE: 6,
            MessagePriority.PRIORITY: 5,
            MessagePriority.ROUTINE: 4,
            MessagePriority.DEFERRED: 3,
        }
        return mapping.get(priority, 3)

    def _truncate_text(self, text: str, max_bytes: int = 228) -> str:
        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text
        suffix = "[TRUNCATED]"
        suffix_bytes = suffix.encode("utf-8")
        keep = max(0, max_bytes - len(suffix_bytes))
        trimmed = encoded[:keep]
        # avoid slicing in middle of utf-8 sequence
        while True:
            try:
                safe_text = trimmed.decode("utf-8")
                break
            except UnicodeDecodeError:
                trimmed = trimmed[:-1]
                if not trimmed:
                    safe_text = ""
                    break
        return safe_text + suffix

    def send(self, message: Message) -> bool:
        if not self._connected:
            return False
        source_text = str(message.metadata.get("_plaintext_body", message.body))
        payload = self._truncate_text(source_text)
        hop_limit = self._priority_hop_limit(message.priority)
        self._signal["hop_count"] = hop_limit
        self._inbox.put(
            {
                "channel_id": message.channel_id or "mesh-local",
                "timestamp": datetime.now(timezone.utc),
                "text": payload,
                "sender_callsign": message.sender_callsign,
                "snr": 12.0,
            }
        )
        return True

    def receive(
        self,
        channel_id: Optional[str],
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Message]:
        if not self._connected:
            return []
        messages: List[Message] = []
        drained: List[dict] = []
        while not self._inbox.empty():
            drained.append(self._inbox.get())
        for item in drained:
            if channel_id and item["channel_id"] != channel_id:
                continue
            ts = item["timestamp"]
            if since and ts <= since:
                continue
            snr = float(item.get("snr", 0.0))
            self._signal["snr"] = snr
            self._signal["rssi"] = -80.0 + snr
            msg = Message(
                message_id=f"mesh-{int(ts.timestamp() * 1000)}",
                timestamp=ts,
                sender_id=item["sender_callsign"],
                sender_callsign=item["sender_callsign"],
                recipient_ids=[],
                channel_id=item["channel_id"],
                message_type=MessageType.REPORT,
                priority=MessagePriority.ROUTINE,
                status=MessageStatus.DELIVERED,
                subject="Meshtastic inbound",
                body=item["text"],
                language="auto",
                relay_backend="meshtastic",
                encryption_protocol="none",
                metadata={"snr": snr, "signal_strength": max(0.0, min(1.0, (snr + 20) / 40.0))},
            )
            messages.append(msg)
            if len(messages) >= limit:
                break
        return messages

    def get_mesh_nodes(self) -> List[dict]:
        return list(self._nodes.values())

    def create_channel(self, name: str, channel_type: ChannelType, members: List[str]) -> Channel:
        channel = Channel(
            channel_id=f"mesh-{name.lower().replace(' ', '-')}",
            name=name,
            channel_type=channel_type,
            members=list(members),
            relay_backend="meshtastic",
            encryption_required=True,
            priority_default=MessagePriority.ROUTINE,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        self._channels[channel.channel_id] = channel
        return channel

    def list_channels(self) -> List[Channel]:
        return list(self._channels.values())

    def get_signal_quality(self) -> dict:
        return dict(self._signal)

    def get_status(self) -> RelayStatus:
        if self._connected:
            return RelayStatus.ONLINE
        return RelayStatus.OFFLINE

