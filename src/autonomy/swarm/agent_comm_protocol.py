"""
S3M structured agent-to-agent communication protocol.

Provides typed, serializable, thread-safe messaging for tactical autonomy.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Set
import uuid

from pydantic import BaseModel, Field


LOGGER = logging.getLogger(__name__)


class MessageType(str, Enum):
    INFORM = "inform"
    REQUEST = "request"
    PROPOSE = "propose"
    ACCEPT = "accept"
    REJECT = "reject"
    ALERT = "alert"
    HEARTBEAT = "heartbeat"
    CFP = "call_for_proposal"
    BID = "bid"
    AWARD = "award"


class AgentMessage(BaseModel):
    """Serializable tactical message between swarm agents."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    sender_id: str
    receiver_id: str
    message_type: MessageType
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    priority: int = Field(default=5, ge=1, le=10)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttl_ms: float = Field(default=30000.0, gt=0.0)


class AgentCommProtocol:
    """
    Thread-safe message bus for tactical inter-agent coordination.

    Tactical context: bounded inboxes and TTL enforcement reduce stale command
    risk when networks are contested or partially degraded.
    """

    def __init__(self, inbox_capacity: int = 1000) -> None:
        capacity = max(10, int(inbox_capacity))
        self._inboxes: Dict[str, Deque[AgentMessage]] = defaultdict(lambda: deque(maxlen=capacity))
        self._inbox_capacity = capacity
        self._registered: Set[str] = set()
        self._stats: Dict[str, int] = defaultdict(int)
        self._audit_log: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def _log_bilingual(self, message_en: str, message_ar: str, **payload: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_en": message_en,
            "message_ar": message_ar,
            "payload": dict(payload),
        }
        self._audit_log.append(entry)
        if len(self._audit_log) > 5000:
            self._audit_log = self._audit_log[-5000:]
        LOGGER.info("%s | %s | payload=%s", message_en, message_ar, payload)

    @staticmethod
    def _timestamp_ms(iso_ts: str) -> float:
        return datetime.fromisoformat(iso_ts).timestamp() * 1000.0

    def register_agent(self, agent_id: str) -> None:
        """Register an agent endpoint."""
        aid = str(agent_id)
        if not aid:
            raise ValueError("agent_id must be non-empty")
        with self._lock:
            self._registered.add(aid)
            if aid not in self._inboxes:
                self._inboxes[aid] = deque(maxlen=self._inbox_capacity)

    def register_swarm(self, coordinator: Any) -> int:
        """Register all known agents from a SwarmCoordinator instance."""
        count = 0
        for agent in coordinator.get_agents():
            self.register_agent(agent.agent_id)
            count += 1
        return count

    def send(self, message: AgentMessage) -> bool:
        """Send unicast or broadcast message."""
        with self._lock:
            if message.sender_id not in self._registered:
                self._stats["dropped"] += 1
                return False

            self._stats["total_sent"] += 1
            self._stats[f"type_{message.message_type.value}"] += 1

            if message.receiver_id == "*":
                delivered = 0
                for agent_id in self._registered:
                    if agent_id == message.sender_id:
                        continue
                    self._inboxes[agent_id].append(message)
                    delivered += 1
                self._stats["broadcasts"] += 1
                self._stats["total_delivered"] += delivered
                self._log_bilingual(
                    "Broadcast delivered",
                    "تم تسليم البث",
                    sender=message.sender_id,
                    delivered=delivered,
                )
                return True

            if message.receiver_id not in self._registered:
                self._stats["dropped"] += 1
                return False
            self._inboxes[message.receiver_id].append(message)
            self._stats["total_delivered"] += 1
            return True

    def send_json(self, message_json: str) -> bool:
        """Deserialize and send message from JSON."""
        message = AgentMessage.model_validate_json(message_json)
        return self.send(message)

    def receive(
        self,
        agent_id: str,
        message_type: Optional[MessageType] = None,
        limit: int = 10,
    ) -> List[AgentMessage]:
        """Receive up to `limit` valid messages from an inbox."""
        if limit <= 0:
            return []

        with self._lock:
            inbox = self._inboxes.get(agent_id)
            if inbox is None:
                return []
            now_ms = time.time() * 1000.0
            selected: List[AgentMessage] = []
            remaining: Deque[AgentMessage] = deque(maxlen=self._inbox_capacity)

            for msg in inbox:
                try:
                    age_ms = now_ms - self._timestamp_ms(msg.timestamp)
                except Exception:
                    age_ms = 0.0
                if age_ms > msg.ttl_ms:
                    self._stats["expired"] += 1
                    continue

                if message_type and msg.message_type != message_type:
                    remaining.append(msg)
                    continue
                if len(selected) < limit:
                    selected.append(msg)
                    self._stats["total_received"] += 1
                else:
                    remaining.append(msg)

            self._inboxes[agent_id] = remaining
            return selected

    def get_conversation(self, agent_id: str, correlation_id: str) -> List[AgentMessage]:
        """Read thread-related messages currently in inbox."""
        with self._lock:
            inbox = self._inboxes.get(agent_id, deque())
            return [msg for msg in inbox if msg.correlation_id == correlation_id]

    def publish_arbitration_result(
        self,
        sender_id: str,
        arbitrator_result: Dict[str, Any],
        receiver_id: str = "*",
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish arbitration result as a typed AWARD message."""
        message = AgentMessage(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=MessageType.AWARD,
            payload=dict(arbitrator_result),
            correlation_id=correlation_id,
            priority=3,
        )
        return self.send(message)

    def get_stats(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._stats)

    def get_audit_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._audit_log)

    def serialize_message(self, message: AgentMessage) -> str:
        """Serialize message to JSON string for tactical transport."""
        return json.dumps(message.model_dump(mode="json"), ensure_ascii=False)

    def deserialize_message(self, payload: str) -> AgentMessage:
        """Deserialize JSON payload to a typed AgentMessage."""
        return AgentMessage.model_validate_json(payload)

    def agent_count(self) -> int:
        with self._lock:
            return len(self._registered)
