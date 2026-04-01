"""Data models for S3M Layer 08 secure communications."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from uuid import uuid4

if TYPE_CHECKING:
    from services.comms.nlp.arabic_nlp_engine import ArabicNLPEngine


class MessagePriority(IntEnum):
    """Military precedence where larger values indicate higher urgency."""

    DEFERRED = 1
    ROUTINE = 2
    PRIORITY = 3
    IMMEDIATE = 4
    FLASH = 5


class MessageType(str, Enum):
    ORDER = "ORDER"
    REPORT = "REPORT"
    REQUEST = "REQUEST"
    INTEL = "INTEL"
    ALERT = "ALERT"
    SITREP = "SITREP"
    LOGISTIC = "LOGISTIC"
    ADMIN = "ADMIN"
    VOICE_TRANSCRIPT = "VOICE_TRANSCRIPT"
    SYSTEM = "SYSTEM"


class MessageStatus(str, Enum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


@dataclass
class Message:
    message_id: str
    timestamp: datetime
    sender_id: str
    sender_callsign: str
    recipient_ids: List[str]
    channel_id: Optional[str]
    message_type: MessageType
    priority: MessagePriority
    status: MessageStatus
    subject: str
    body: str
    language: str
    relay_backend: str
    encryption_protocol: str
    attachments: List[dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    summary: Optional[str] = None
    extracted_entities: List[dict] = field(default_factory=list)
    extracted_intent: Optional[str] = None
    urgency_score: float = 0.0
    classification: str = "UNCLASSIFIED - FOUO"

    def __post_init__(self) -> None:
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        if isinstance(self.message_type, str):
            self.message_type = MessageType(self.message_type)
        if isinstance(self.priority, str):
            self.priority = MessagePriority[str(self.priority).upper()]
        if isinstance(self.status, str):
            self.status = MessageStatus(self.status)
        self.recipient_ids = [str(v) for v in self.recipient_ids]
        self.urgency_score = max(0.0, min(1.0, float(self.urgency_score)))

    @classmethod
    def create(
        cls,
        sender_id: str,
        sender_callsign: str,
        recipient_ids: List[str],
        body: str,
        message_type: MessageType,
        priority: MessagePriority,
        subject: str = "",
        channel_id: Optional[str] = None,
        language: str = "auto",
        relay_backend: str = "simulated",
        encryption_protocol: str = "none",
        classification: str = "UNCLASSIFIED - FOUO",
    ) -> "Message":
        return cls(
            message_id=f"msg-{uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            sender_id=sender_id,
            sender_callsign=sender_callsign,
            recipient_ids=list(recipient_ids),
            channel_id=channel_id,
            message_type=message_type,
            priority=priority,
            status=MessageStatus.QUEUED,
            subject=subject,
            body=body,
            language=language,
            relay_backend=relay_backend,
            encryption_protocol=encryption_protocol,
            classification=classification,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "sender_id": self.sender_id,
            "sender_callsign": self.sender_callsign,
            "recipient_ids": list(self.recipient_ids),
            "channel_id": self.channel_id,
            "message_type": self.message_type.value,
            "priority": self.priority.name,
            "status": self.status.value,
            "subject": self.subject,
            "body": self.body,
            "language": self.language,
            "relay_backend": self.relay_backend,
            "encryption_protocol": self.encryption_protocol,
            "attachments": list(self.attachments),
            "metadata": dict(self.metadata),
            "summary": self.summary,
            "extracted_entities": list(self.extracted_entities),
            "extracted_intent": self.extracted_intent,
            "urgency_score": self.urgency_score,
            "classification": self.classification,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Message":
        return cls(
            message_id=str(payload["message_id"]),
            timestamp=payload["timestamp"],
            sender_id=str(payload.get("sender_id", "")),
            sender_callsign=str(payload.get("sender_callsign", "")),
            recipient_ids=list(payload.get("recipient_ids", [])),
            channel_id=payload.get("channel_id"),
            message_type=payload.get("message_type", MessageType.SYSTEM.value),
            priority=payload.get("priority", MessagePriority.ROUTINE.name),
            status=payload.get("status", MessageStatus.QUEUED.value),
            subject=str(payload.get("subject", "")),
            body=str(payload.get("body", "")),
            language=str(payload.get("language", "auto")),
            relay_backend=str(payload.get("relay_backend", "simulated")),
            encryption_protocol=str(payload.get("encryption_protocol", "none")),
            attachments=list(payload.get("attachments", [])),
            metadata=dict(payload.get("metadata", {})),
            summary=payload.get("summary"),
            extracted_entities=list(payload.get("extracted_entities", [])),
            extracted_intent=payload.get("extracted_intent"),
            urgency_score=float(payload.get("urgency_score", 0.0)),
            classification=str(payload.get("classification", "UNCLASSIFIED - FOUO")),
        )

    def to_log_safe(self) -> Dict[str, Any]:
        """Return audit-safe payload that never contains message plaintext."""
        payload = self.to_dict()
        payload.pop("body", None)
        metadata = payload.get("metadata", {}) or {}
        if isinstance(metadata, dict):
            payload["metadata"] = {
                key: value
                for key, value in metadata.items()
                if not str(key).startswith("_")
            }
        payload["body_redacted"] = True
        payload["body_length"] = len(self.body)
        return payload

    def is_arabic(self) -> bool:
        text = f"{self.subject} {self.body}"
        return any(0x0600 <= ord(ch) <= 0x06FF for ch in text)

    def age_seconds(self) -> float:
        return max(0.0, (datetime.now(timezone.utc) - self.timestamp).total_seconds())


class ChannelType(str, Enum):
    COMMAND_NET = "COMMAND_NET"
    INTEL_NET = "INTEL_NET"
    LOGISTICS_NET = "LOGISTICS_NET"
    ADMIN_NET = "ADMIN_NET"
    ALERT_NET = "ALERT_NET"
    MESH_LOCAL = "MESH_LOCAL"
    DIRECT = "DIRECT"


@dataclass
class Channel:
    channel_id: str
    name: str
    channel_type: ChannelType
    members: List[str]
    relay_backend: str
    encryption_required: bool
    priority_default: MessagePriority
    active: bool
    created_at: datetime

    def __post_init__(self) -> None:
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        if isinstance(self.channel_type, str):
            self.channel_type = ChannelType(self.channel_type)
        if isinstance(self.priority_default, str):
            self.priority_default = MessagePriority[str(self.priority_default).upper()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "channel_type": self.channel_type.value,
            "members": list(self.members),
            "relay_backend": self.relay_backend,
            "encryption_required": self.encryption_required,
            "priority_default": self.priority_default.name,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }

    def member_count(self) -> int:
        return len(self.members)


class RelayBackend(str, Enum):
    MATRIX = "matrix"
    MESHTASTIC = "meshtastic"
    XMPP = "xmpp"
    ROCKET_CHAT = "rocket_chat"
    P2P_DIRECT = "p2p"
    SIMULATED = "simulated"


class RelayStatus(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    ERROR = "ERROR"


class NodeType(str, Enum):
    COMMAND_CENTER = "command_center"
    FIELD_UNIT = "field_unit"
    UAV_PLATFORM = "uav_platform"
    UGV_PLATFORM = "ugv_platform"
    RELAY_NODE = "relay_node"
    SENSOR_NODE = "sensor_node"
    ANALYST_STATION = "analyst_station"


@dataclass
class CommsNode:
    node_id: str
    callsign: str
    node_type: NodeType
    relay_backends: List[RelayBackend]
    position: Optional[Tuple[float, float, float]]
    last_heartbeat: datetime
    status: str
    signal_strength: float
    battery_pct: Optional[float] = None

    def __post_init__(self) -> None:
        if isinstance(self.last_heartbeat, str):
            self.last_heartbeat = datetime.fromisoformat(self.last_heartbeat.replace("Z", "+00:00"))
        if isinstance(self.node_type, str):
            self.node_type = NodeType(self.node_type)
        self.signal_strength = max(0.0, min(1.0, float(self.signal_strength)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "callsign": self.callsign,
            "node_type": self.node_type.value,
            "relay_backends": [backend.value for backend in self.relay_backends],
            "position": self.position,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "status": self.status,
            "signal_strength": float(self.signal_strength),
            "battery_pct": self.battery_pct,
        }

    def is_online(self) -> bool:
        if self.status.lower() not in {"online", "active", "connected", "nominal"}:
            return False
        return self.time_since_heartbeat() <= 300.0

    def time_since_heartbeat(self) -> float:
        return max(0.0, (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds())


@dataclass
class MessageSummary:
    message_id: str
    original_language: str
    summary_ar: Optional[str]
    summary_en: Optional[str]
    entities: List[dict]
    intent: str
    urgency_score: float
    sentiment: str
    model_used: str
    processing_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "original_language": self.original_language,
            "summary_ar": self.summary_ar,
            "summary_en": self.summary_en,
            "entities": list(self.entities),
            "intent": self.intent,
            "urgency_score": float(self.urgency_score),
            "sentiment": self.sentiment,
            "model_used": self.model_used,
            "processing_time_ms": float(self.processing_time_ms),
        }
