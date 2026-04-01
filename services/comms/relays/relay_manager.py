"""Relay manager coordinating multiple secure messaging backends."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.comms.models import Channel, ChannelType, Message, RelayBackend, RelayStatus
from services.comms.relays.matrix_adapter import MatrixAdapter
from services.comms.relays.meshtastic_adapter import MeshtasticAdapter
from services.comms.relays.p2p_relay_adapter import P2PRelayAdapter
from services.comms.relays.rocketchat_adapter import RocketChatAdapter
from services.comms.relays.simulated_relay import SimulatedRelay
from services.comms.relays.xmpp_adapter import XMPPAdapter


class RelayManager:
    """Coordinate backend selection and tactical fallback behavior."""

    def __init__(self) -> None:
        self.adapters: Dict[RelayBackend, Any] = {
            RelayBackend.SIMULATED: SimulatedRelay(),
            RelayBackend.MATRIX: MatrixAdapter(),
            RelayBackend.MESHTASTIC: MeshtasticAdapter(),
            RelayBackend.XMPP: XMPPAdapter(),
            RelayBackend.ROCKET_CHAT: RocketChatAdapter(),
            RelayBackend.P2P_DIRECT: P2PRelayAdapter(),
        }
        self.connected: Dict[RelayBackend, bool] = {}
        self.stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"sent": 0, "failed": 0})
        self.fallback_order: List[RelayBackend] = [
            RelayBackend.MATRIX,
            RelayBackend.XMPP,
            RelayBackend.ROCKET_CHAT,
            RelayBackend.MESHTASTIC,
            RelayBackend.P2P_DIRECT,
            RelayBackend.SIMULATED,
        ]
        self.connect_backend(RelayBackend.SIMULATED)

    def _to_backend(self, backend: RelayBackend | str) -> RelayBackend:
        if isinstance(backend, RelayBackend):
            return backend
        raw = str(backend).strip().lower()
        for candidate in RelayBackend:
            if candidate.value == raw:
                return candidate
        raise ValueError(f"unknown relay backend: {backend}")

    def connect_backend(self, backend: RelayBackend, config: Optional[Dict[str, Any]] = None) -> bool:
        adapter = self.adapters[backend]
        if config:
            for key, value in config.items():
                if hasattr(adapter, key):
                    setattr(adapter, key, value)
        ok = bool(adapter.connect())
        self.connected[backend] = ok
        return ok

    def disconnect_backend(self, backend: RelayBackend) -> None:
        self.connected[self._to_backend(backend)] = False

    def _send_via(self, message: Message, backend: RelayBackend) -> bool:
        adapter = self.adapters[backend]
        backend_key = backend.value
        try:
            ok = bool(adapter.send(message))
        except Exception:
            ok = False
        if ok:
            self.stats[backend_key]["sent"] += 1
            message.relay_backend = backend.value
        else:
            self.stats[backend_key]["failed"] += 1
        return ok

    def send(self, message: Message, backend: Optional[RelayBackend] = None) -> bool:
        if backend is not None:
            target = self._to_backend(backend)
            return self._send_via(message, target)
        for candidate in self.fallback_order:
            if self._send_via(message, candidate):
                return True
        return False

    def broadcast(self, message: Message, channel_type: Optional[ChannelType] = None) -> Dict[str, Any]:
        targets: List[Channel] = []
        for adapter in self.adapters.values():
            for channel in adapter.list_channels():
                if channel_type is None or channel.channel_type == channel_type:
                    targets.append(channel)
        delivered = 0
        attempted = 0
        for channel in targets:
            cloned = Message.from_dict(message.to_dict())
            cloned.channel_id = channel.channel_id
            cloned.recipient_ids = list(channel.members)
            attempted += 1
            if self.send(cloned):
                delivered += 1
        return {"attempted": attempted, "delivered": delivered, "channel_type": channel_type.value if channel_type else "ALL"}

    def receive(
        self,
        channel_id: Optional[str],
        backend: Optional[RelayBackend | str] = None,
        since: Optional[datetime] = None,
    ) -> List[Message]:
        if backend is not None:
            adapter = self.adapters[self._to_backend(backend)]
            return list(adapter.receive(channel_id=channel_id, since=since, limit=50))
        messages: List[Message] = []
        for adapter in self.adapters.values():
            messages.extend(adapter.receive(channel_id=channel_id, since=since, limit=50))
        return sorted(messages, key=lambda m: m.timestamp)

    def create_channel(
        self,
        name: str,
        channel_type: ChannelType,
        members: List[str],
        backend: Optional[RelayBackend] = None,
    ) -> Channel:
        target = backend or RelayBackend.SIMULATED
        adapter = self.adapters[self._to_backend(target)]
        return adapter.create_channel(name=name, channel_type=channel_type, members=members)

    def list_channels(self, backend: Optional[RelayBackend] = None) -> List[Channel]:
        if backend is not None:
            return list(self.adapters[self._to_backend(backend)].list_channels())
        channels: Dict[str, Channel] = {}
        for adapter in self.adapters.values():
            for channel in adapter.list_channels():
                channels[channel.channel_id] = channel
        return list(channels.values())

    def get_backend_status(self) -> Dict[str, RelayStatus]:
        status: Dict[str, RelayStatus] = {}
        for backend, adapter in self.adapters.items():
            status[backend.value] = adapter.get_status()
        return status

    def get_mesh_topology(self) -> List[dict]:
        topology: List[dict] = []
        meshtastic = self.adapters[RelayBackend.MESHTASTIC]
        for node in meshtastic.get_mesh_nodes():
            topology.append({"backend": RelayBackend.MESHTASTIC.value, **node})
        p2p = self.adapters[RelayBackend.P2P_DIRECT]
        for peer in p2p.get_peers():
            topology.append({"backend": RelayBackend.P2P_DIRECT.value, **peer})
        return topology

    def get_message_stats(self) -> dict:
        payload: Dict[str, Any] = {"backends": {}, "total_sent": 0, "total_failed": 0}
        for backend in RelayBackend:
            stats = self.stats.get(backend.value, {"sent": 0, "failed": 0})
            sent = stats["sent"]
            failed = stats["failed"]
            total = sent + failed
            payload["backends"][backend.value] = {
                "sent": sent,
                "failed": failed,
                "failure_rate": (failed / total) if total else 0.0,
            }
            payload["total_sent"] += sent
            payload["total_failed"] += failed
        return payload

    def health_check(self) -> dict:
        status = self.get_backend_status()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "backend_status": {name: value.value for name, value in status.items()},
            "stats": self.get_message_stats(),
            "mesh_nodes": len(self.get_mesh_topology()),
        }

