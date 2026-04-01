"""Central manager for S3M Layer 08 secure communications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.comms.c2 import C2MessageRouter, CommsSecurityManager, MessageIntelExtractor
from services.comms.models import Channel, ChannelType, Message, MessagePriority, MessageStatus, MessageType, NodeType, RelayBackend
from services.comms.nlp import ArabicNLPEngine, MessageSummarizer
from services.comms.node_manager import CommsNodeManager
from services.comms.relays import RelayManager


class CommsManager:
    """Top-level facade for secure tactical message flow and telemetry."""

    def __init__(self) -> None:
        self.relay_manager = RelayManager()
        self.nlp_engine = ArabicNLPEngine(model_backend="auto")
        self.message_summarizer = MessageSummarizer(engine=self.nlp_engine)
        self.security_manager = CommsSecurityManager()
        self.node_manager = CommsNodeManager()
        self.c2_router = C2MessageRouter(relay_manager=self.relay_manager, nlp_engine=self.nlp_engine, node_manager=self.node_manager)
        self.intel_extractor = MessageIntelExtractor(nlp_engine=self.nlp_engine)
        self._message_log: List[Message] = []

    @staticmethod
    def _parse_message_type(value: MessageType | str) -> MessageType:
        if isinstance(value, MessageType):
            return value
        return MessageType(str(value).upper())

    @staticmethod
    def _parse_priority(value: MessagePriority | str) -> MessagePriority:
        if isinstance(value, MessagePriority):
            return value
        return MessagePriority[str(value).upper()]

    @staticmethod
    def _parse_node_type(value: NodeType | str) -> NodeType:
        if isinstance(value, NodeType):
            return value
        return NodeType(str(value))

    @staticmethod
    def _parse_backends(values: List[RelayBackend | str]) -> List[RelayBackend]:
        parsed: List[RelayBackend] = []
        for value in values:
            if isinstance(value, RelayBackend):
                parsed.append(value)
            else:
                parsed.append(RelayBackend(str(value).lower()))
        return parsed

    def send_message(
        self,
        sender_callsign: str,
        recipients: List[str],
        body: str,
        message_type: MessageType | str,
        priority: MessagePriority | str,
        language: str = "auto",
        channel_id: Optional[str] = None,
        encrypt: bool = True,
    ) -> Dict[str, Any]:
        sender = self.node_manager.get_node_by_callsign(sender_callsign)
        if sender is None:
            raise ValueError(f"unknown sender callsign: {sender_callsign}")
        msg_type = self._parse_message_type(message_type)
        prio = self._parse_priority(priority)
        message = Message(
            message_id=f"msg-{uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            sender_id=sender.node_id,
            sender_callsign=sender.callsign,
            recipient_ids=list(recipients),
            channel_id=channel_id,
            message_type=msg_type,
            priority=prio,
            status=MessageStatus.QUEUED,
            subject=f"{msg_type.value} from {sender.callsign}",
            body=body,
            language=language,
            relay_backend=RelayBackend.SIMULATED.value,
            encryption_protocol="none",
            metadata={},
        )
        if encrypt:
            message = self.security_manager.encrypt_message(message)
        route_result = self.c2_router.route_message(message)
        intel = self.intel_extractor.extract(message)
        self._message_log.append(message)
        payload = dict(route_result)
        payload["intel"] = intel
        return payload

    def send_order(self, sender: str, recipients: List[str], order_text: str, priority: MessagePriority | str) -> Dict[str, Any]:
        return self.send_message(
            sender_callsign=sender,
            recipients=recipients,
            body=order_text,
            message_type=MessageType.ORDER,
            priority=priority,
            language="auto",
            channel_id=None,
            encrypt=True,
        )

    def send_sitrep(self, sender: str, sitrep_text: str) -> Dict[str, Any]:
        result = self.send_message(
            sender_callsign=sender,
            recipients=[],
            body=sitrep_text,
            message_type=MessageType.SITREP,
            priority=MessagePriority.PRIORITY,
            language="auto",
            channel_id=None,
            encrypt=True,
        )
        if self._message_log:
            result["threat_feed"] = self.intel_extractor.feed_to_threat_detection(
                self.intel_extractor.extract(self._message_log[-1]).get("threat_indicators", [])
            )
        return result

    def broadcast_alert(self, sender: str, alert_text: str) -> Dict[str, Any]:
        result = self.send_message(
            sender_callsign=sender,
            recipients=[],
            body=alert_text,
            message_type=MessageType.ALERT,
            priority=MessagePriority.FLASH,
            language="auto",
            channel_id=None,
            encrypt=True,
        )
        return result

    def receive_messages(
        self,
        channel_id: Optional[str] = None,
        backend: Optional[RelayBackend | str] = None,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Message]:
        target_channel = channel_id or "direct"
        messages = self.relay_manager.receive(channel_id=target_channel, backend=backend, since=since)
        output = messages[-limit:]
        for msg in output:
            self.message_summarizer.summarize_message(msg)
        return output

    def create_channel(
        self,
        name: str,
        channel_type: ChannelType | str,
        members: List[str],
        backend: Optional[RelayBackend | str] = None,
    ) -> Channel:
        ctype = channel_type if isinstance(channel_type, ChannelType) else ChannelType(str(channel_type).upper())
        relay_backend = backend
        if isinstance(backend, str):
            relay_backend = RelayBackend(backend.lower())
        return self.relay_manager.create_channel(name=name, channel_type=ctype, members=members, backend=relay_backend)

    def get_channels(self) -> List[Channel]:
        return self.relay_manager.list_channels()

    def get_comms_brief(self, minutes: int = 60) -> str:
        cutoff = datetime.now(timezone.utc).timestamp() - max(1, minutes) * 60
        messages = [m for m in self._message_log if m.timestamp.timestamp() >= cutoff]
        channels = self.get_channels()
        return self.message_summarizer.generate_comms_brief(channels=channels, messages=messages)

    def get_network_status(self) -> Dict[str, Any]:
        backend_status = {k: v.value for k, v in self.relay_manager.get_backend_status().items()}
        return {
            "relay": {
                "backend_status": backend_status,
                "health": self.relay_manager.health_check(),
            },
            "nodes": self.node_manager.get_network_topology(),
            "message_stats": self.relay_manager.get_message_stats(),
            "nlp": self.nlp_engine.health_check(),
        }

    def register_node(
        self,
        callsign: str,
        node_type: NodeType | str,
        backends: List[RelayBackend | str],
        position: Optional[tuple] = None,
    ):
        parsed_type = self._parse_node_type(node_type)
        parsed_backends = self._parse_backends(backends)
        return self.node_manager.register_node(
            callsign=callsign,
            node_type=parsed_type,
            relay_backends=parsed_backends,
            position=position,
        )

    def get_nodes(self):
        return self.node_manager.get_nodes()

    def health_check(self) -> Dict[str, Any]:
        return {
            "relay_manager": self.relay_manager.health_check(),
            "nlp": self.nlp_engine.health_check(),
            "c2_router": self.c2_router.health_check(),
            "node_manager": self.node_manager.get_stats(),
            "message_log_size": len(self._message_log),
        }
