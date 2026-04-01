"""C2 routing logic for secure tactical message distribution."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.autonomy.models import CommandType

from services.comms.models import (
    ChannelType,
    Message,
    MessageSummary,
    MessagePriority,
    MessageStatus,
    MessageType,
    RelayBackend,
)
from services.comms.nlp import ArabicNLPEngine, MessageSummarizer
from services.comms.relays import RelayManager

LOGGER = logging.getLogger(__name__)


class C2MessageRouter:
    """Routes military messages with NLP enrichment and secure audit logging."""

    def __init__(
        self,
        relay_manager: Optional[RelayManager] = None,
        nlp_engine: Optional[ArabicNLPEngine] = None,
        node_manager: Optional[Any] = None,
    ) -> None:
        self.relay_manager = relay_manager or RelayManager()
        self.nlp_engine = nlp_engine or ArabicNLPEngine(model_backend="auto")
        self.summarizer = MessageSummarizer(engine=self.nlp_engine)
        self.node_manager = node_manager
        self.routing_log: List[Dict[str, Any]] = []
        self.channel_map: Dict[MessageType, ChannelType] = {
            MessageType.ORDER: ChannelType.COMMAND_NET,
            MessageType.INTEL: ChannelType.INTEL_NET,
            MessageType.SITREP: ChannelType.INTEL_NET,
            MessageType.ALERT: ChannelType.ALERT_NET,
        }

    def _audit(self, message: Message, result: Dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message.to_log_safe(),
            "routing_result": result,
        }
        self.routing_log.append(entry)
        if len(self.routing_log) > 2000:
            self.routing_log = self.routing_log[-2000:]

    def _resolve_channel_type(self, message: Message) -> ChannelType:
        return self.channel_map.get(message.message_type, ChannelType.ADMIN_NET)

    def _route_flash(self, message: Message) -> Dict[str, Any]:
        routed_to: List[str] = []
        for backend in RelayBackend:
            if self.relay_manager.send(message, backend=backend):
                routed_to.append(backend.value)
        return {
            "message_id": message.message_id,
            "routed_to": routed_to,
            "backend": "flash_all",
            "nlp_summary": message.summary,
            "urgency": message.urgency_score,
            "status": MessageStatus.DELIVERED.value if routed_to else MessageStatus.FAILED.value,
        }

    def route_message(self, message: Message) -> Dict[str, Any]:
        if not message.classification:
            raise ValueError("message classification is required")
        if not message.sender_callsign:
            raise ValueError("message sender_callsign is required")
        if self.node_manager is not None and self.node_manager.get_node_by_callsign(message.sender_callsign) is None:
            raise ValueError(f"sender not registered: {message.sender_callsign}")

        self.summarizer.summarize_message(message)
        channel_type = self._resolve_channel_type(message)
        routed_to: List[str] = []
        used_backend = "none"

        if message.priority == MessagePriority.FLASH:
            result = self._route_flash(message)
            self._audit(message, result)
            return result

        if message.message_type == MessageType.ALERT:
            broadcast_result = self.relay_manager.broadcast(message, channel_type=ChannelType.ALERT_NET)
            status = MessageStatus.DELIVERED if broadcast_result.get("delivered", 0) > 0 else MessageStatus.FAILED
            result = {
                "message_id": message.message_id,
                "routed_to": [ChannelType.ALERT_NET.value],
                "backend": "broadcast",
                "nlp_summary": message.summary,
                "urgency": message.urgency_score,
                "status": status.value,
            }
            self._audit(message, result)
            return result

        if message.extracted_intent == "request_support" and message.urgency_score > 0.8:
            channel_type = ChannelType.COMMAND_NET

        channels = [
            channel
            for channel in self.relay_manager.list_channels()
            if channel.channel_type == channel_type and channel.active
        ]
        if channels:
            routed_to = [channel.channel_id for channel in channels]
            message.channel_id = channels[0].channel_id
            message.recipient_ids = list(channels[0].members)
        else:
            routed_to = [channel_type.value]

        sent = self.relay_manager.send(message)
        used_backend = message.relay_backend
        message.status = MessageStatus.DELIVERED if sent else MessageStatus.FAILED
        result = {
            "message_id": message.message_id,
            "routed_to": routed_to,
            "backend": used_backend,
            "nlp_summary": message.summary,
            "urgency": message.urgency_score,
            "status": message.status.value,
        }
        self._audit(message, result)
        return result

    def route_order(
        self,
        order_text: str,
        sender: str,
        recipients: List[str],
        priority: MessagePriority = MessagePriority.PRIORITY,
    ) -> Dict[str, Any]:
        parsed = self._parse_order_for_swarm(order_text)
        message = Message.create(
            sender_id=sender,
            sender_callsign=sender,
            recipient_ids=recipients,
            body=order_text,
            message_type=MessageType.ORDER,
            priority=priority,
            subject="Tactical Order",
            encryption_protocol="aes256",
        )
        message.metadata["parsed_order"] = parsed
        return self.route_message(message)

    def _parse_order_for_swarm(self, text: str) -> Dict[str, Any]:
        lower = text.lower()
        command = CommandType.HOLD.value
        if "patrol" in lower or "recon" in lower:
            command = CommandType.MOVE_TO.value
        elif "withdraw" in lower:
            command = CommandType.RTB.value
        elif "engage" in lower:
            command = CommandType.ENGAGE.value
        return {
            "command_id": f"cmd-{uuid4().hex[:10]}",
            "command_type": command,
            "target_agents": ["all"],
            "parameters": {"text": text},
            "issued_by": "c2_router",
            "priority": 3,
            "ttl_seconds": 120.0,
        }

    def route_sitrep(self, sitrep_text: str, sender: str) -> Dict[str, Any]:
        message = Message.create(
            sender_id=sender,
            sender_callsign=sender,
            recipient_ids=["intel"],
            body=sitrep_text,
            message_type=MessageType.SITREP,
            priority=MessagePriority.PRIORITY,
            subject="SITREP",
            encryption_protocol="aes256",
        )
        return self.route_message(message)

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "operational",
            "routing_log_entries": len(self.routing_log),
            "relay_status": {k: v.value for k, v in self.relay_manager.get_backend_status().items()},
            "nlp_backend": self.nlp_engine.get_model_info().get("active_backend", "unknown"),
            "plaintext_logging_enforced": True,
        }

    def get_routing_log(self, limit: int = 50) -> List[dict]:
        return self.routing_log[-max(1, limit) :]

    def get_channel_traffic(self, channel_id: str, minutes: int = 60) -> Dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(minutes=max(1, int(minutes)))
        messages = self.relay_manager.receive(channel_id=channel_id, since=since)
        safe = [msg.to_log_safe() for msg in messages]
        summary = self.summarizer.summarize_channel_traffic(messages, time_window_minutes=minutes)
        return {
            "channel_id": channel_id,
            "window_minutes": minutes,
            "message_count": len(messages),
            "messages": safe,
            "summary": summary,
        }

