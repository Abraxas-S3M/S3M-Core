"""Peer-to-peer UDP relay adapter for contested environments."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.comms.models import (
    Channel,
    ChannelType,
    Message,
    MessagePriority,
    MessageStatus,
    MessageType,
    RelayStatus,
)


class P2PRelayAdapter:
    """Direct local UDP relay for resilient low-footprint message passing."""

    def __init__(self, listen_port: int = 9999) -> None:
        self.listen_port = int(listen_port)
        self._status = RelayStatus.OFFLINE
        self._sock: Optional[socket.socket] = None
        self._peers: Dict[str, Tuple[str, int]] = {}
        self._channels: Dict[str, Channel] = {}
        self._received: List[Message] = []
        self._key = hashlib.sha256(b"S3M_P2P_AES256_PLACEHOLDER").digest()

    def _xor_cipher(self, data: bytes) -> bytes:
        stream = bytearray()
        counter = 0
        while len(stream) < len(data):
            block = hashlib.sha256(self._key + counter.to_bytes(8, "big")).digest()
            stream.extend(block)
            counter += 1
        return bytes(a ^ b for a, b in zip(data, stream[: len(data)]))

    def connect(self) -> bool:
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.bind(("127.0.0.1", self.listen_port))
            self._sock.setblocking(False)
            self._status = RelayStatus.ONLINE
            return True
        except Exception:
            self._status = RelayStatus.ERROR
            self._sock = None
            return False

    def register_peer(self, node_id: str, address: str, port: int) -> None:
        self._peers[str(node_id)] = (str(address), int(port))

    def get_peers(self) -> List[dict]:
        return [{"node_id": nid, "address": addr, "port": port} for nid, (addr, port) in self._peers.items()]

    def create_channel(self, name: str, channel_type: ChannelType, members: List[str]) -> Channel:
        channel = Channel(
            channel_id=f"p2p-{name.lower().replace(' ', '-')}",
            name=name,
            channel_type=channel_type,
            members=list(members),
            relay_backend="p2p",
            encryption_required=True,
            priority_default=MessagePriority.PRIORITY,
            active=True,
            created_at=datetime.now(timezone.utc),
        )
        self._channels[channel.channel_id] = channel
        return channel

    def list_channels(self) -> List[Channel]:
        return list(self._channels.values())

    def _serialize_message(self, message: Message) -> bytes:
        payload = message.to_dict()
        payload["timestamp"] = message.timestamp.isoformat()
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encrypted = self._xor_cipher(raw)
        return base64.b64encode(encrypted)

    def _deserialize_message(self, data: bytes) -> Optional[Message]:
        try:
            decrypted = self._xor_cipher(base64.b64decode(data))
            payload = json.loads(decrypted.decode("utf-8"))
            return Message.from_dict(payload)
        except Exception:
            return None

    def send(self, message: Message) -> bool:
        if self._status != RelayStatus.ONLINE or self._sock is None:
            return False
        blob = self._serialize_message(message)
        sent_any = False
        targets = [self._peers[peer] for peer in message.recipient_ids if peer in self._peers]
        if not targets:
            targets = [("127.0.0.1", self.listen_port)]
        for addr, port in targets:
            try:
                self._sock.sendto(blob, (addr, port))
                sent_any = True
            except Exception:
                continue
        if sent_any:
            message.status = MessageStatus.DELIVERED
            message.relay_backend = "p2p"
            self._received.append(message)
        return sent_any

    def receive(self, channel_id: Optional[str], since: Optional[datetime] = None, limit: int = 50) -> List[Message]:
        messages = list(self._received)
        if self._status == RelayStatus.ONLINE and self._sock is not None:
            while True:
                try:
                    data, _ = self._sock.recvfrom(65535)
                except BlockingIOError:
                    break
                except Exception:
                    break
                message = self._deserialize_message(data)
                if message is not None:
                    self._received.append(message)
                    messages.append(message)
        if since is not None:
            messages = [m for m in messages if m.timestamp >= since]
        if channel_id:
            messages = [m for m in messages if m.channel_id == channel_id]
        return messages[-limit:]

    def get_status(self) -> RelayStatus:
        return self._status if self._sock is not None else RelayStatus.OFFLINE
