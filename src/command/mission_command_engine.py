"""
S3M Mission Command Engine — Gap 1 of 7
Event-driven, asyncio-based top-level C2 brain.
Ingests all layer streams, maintains authoritative state,
propagates tasking, and enforces human-in-the-loop approvals.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("s3m.command.mce")


# ─── Domain Types ────────────────────────────────────────────────────────────

class EventType(str, Enum):
    THREAT_DETECTED = "THREAT_DETECTED"
    ASSET_STATUS = "ASSET_STATUS"
    LOGISTICS_UPDATE = "LOGISTICS_UPDATE"
    TASK_ORDER = "TASK_ORDER"
    ROE_CHECK = "ROE_CHECK"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_DENIED = "APPROVAL_DENIED"


class ApprovalState(str, Enum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


@dataclass
class MCEvent:
    event_type: EventType
    source_layer: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    classification: str = "UNCLASSIFIED-FOUO"


@dataclass
class ApprovalTicket:
    ticket_id: str
    action: str
    requestor: str
    payload: Dict[str, Any]
    state: ApprovalState = ApprovalState.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolver: Optional[str] = None
    ttl_seconds: int = 300


@dataclass
class AuthoritativeState:
    """Single source of truth for COP (Common Operating Picture)."""

    assets: Dict[str, Dict] = field(default_factory=dict)
    threats: Dict[str, Dict] = field(default_factory=dict)
    tasks: Dict[str, Dict] = field(default_factory=dict)
    logistics: Dict[str, Any] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Append-Only Audit Log ───────────────────────────────────────────────────

class AuditLog:
    """Cryptographically chained append-only log (poor-man's blockchain for air-gap)."""

    def __init__(self, log_path: str = "data/mce_audit.jsonl") -> None:
        self._path = log_path
        self._prev_hash = "GENESIS"

    def append(self, event: MCEvent, note: str = "") -> str:
        payload_blob = event.payload if isinstance(event.payload, dict) else {"payload": str(event.payload)}
        record = {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "source_layer": event.source_layer,
            "timestamp": event.timestamp,
            "payload_digest": hashlib.sha256(
                json.dumps(payload_blob, sort_keys=True).encode()
            ).hexdigest(),
            "note": note,
            "prev_hash": self._prev_hash,
        }
        record_json = json.dumps(record, sort_keys=True)
        self._prev_hash = hashlib.sha256(record_json.encode()).hexdigest()
        record["chain_hash"] = self._prev_hash
        try:
            log_dir = os.path.dirname(self._path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            logger.warning("Audit log write failed — %s", self._path)
        return self._prev_hash


# ─── Human-in-the-Loop Approval Gate ─────────────────────────────────────────

class ApprovalGate:
    def __init__(self) -> None:
        self._tickets: Dict[str, ApprovalTicket] = {}
        self._callbacks: Dict[str, asyncio.Future[ApprovalState]] = {}

    def create_ticket(self, action: str, requestor: str, payload: Dict[str, Any]) -> ApprovalTicket:
        ticket = ApprovalTicket(
            ticket_id=str(uuid4()),
            action=action,
            requestor=requestor,
            payload=payload,
        )
        self._tickets[ticket.ticket_id] = ticket
        return ticket

    async def await_approval(
        self,
        ticket: ApprovalTicket,
        loop: asyncio.AbstractEventLoop,
    ) -> ApprovalState:
        future: asyncio.Future[ApprovalState] = loop.create_future()
        self._callbacks[ticket.ticket_id] = future
        try:
            return await asyncio.wait_for(future, timeout=ticket.ttl_seconds)
        except asyncio.TimeoutError:
            ticket.state = ApprovalState.EXPIRED
            return ApprovalState.EXPIRED
        finally:
            self._callbacks.pop(ticket.ticket_id, None)

    def resolve(self, ticket_id: str, granted: bool, resolver: str) -> Optional[ApprovalTicket]:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None
        ticket.state = ApprovalState.GRANTED if granted else ApprovalState.DENIED
        ticket.resolved_at = datetime.now(timezone.utc).isoformat()
        ticket.resolver = resolver
        callback = self._callbacks.get(ticket_id)
        if callback and not callback.done():
            callback.set_result(ticket.state)
        return ticket

    def get_pending(self) -> List[ApprovalTicket]:
        return [ticket for ticket in self._tickets.values() if ticket.state == ApprovalState.PENDING]


# ─── In-Process Pub/Sub Bus (swap for NATS in production) ───────────────────

class EventBus:
    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Callable[..., Any]) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event: MCEvent) -> None:
        handlers = self._subscribers.get(event.event_type, [])
        if not handlers:
            return
        loop = asyncio.get_running_loop()
        tasks = [
            asyncio.create_task(handler(event))
            if asyncio.iscoroutinefunction(handler)
            else loop.run_in_executor(None, handler, event)
            for handler in handlers
        ]
        await asyncio.gather(*tasks)


# ─── Mission Command Engine ──────────────────────────────────────────────────

class MissionCommandEngine:
    """
    Singleton C2 brain.

    Usage:
        mce = MissionCommandEngine()
        asyncio.run(mce.start())
        await mce.ingest(MCEvent(EventType.THREAT_DETECTED, "layer-02", {...}))
    """

    _instance: Optional["MissionCommandEngine"] = None

    def __new__(cls) -> "MissionCommandEngine":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self.state = AuthoritativeState()
        self.bus = EventBus()
        self.audit = AuditLog()
        self.gate = ApprovalGate()
        self._queue: asyncio.Queue[MCEvent] = asyncio.Queue()
        self._running = False
        self._register_internal_handlers()
        self._initialized = True

    # ── Internal Handlers ─────────────────────────────────────────────────────

    def _register_internal_handlers(self) -> None:
        self.bus.subscribe(EventType.THREAT_DETECTED, self._on_threat)
        self.bus.subscribe(EventType.ASSET_STATUS, self._on_asset_status)
        self.bus.subscribe(EventType.LOGISTICS_UPDATE, self._on_logistics)
        self.bus.subscribe(EventType.TASK_ORDER, self._on_task_order)

    async def _on_threat(self, event: MCEvent) -> None:
        threat_id = event.payload.get("threat_id", event.event_id)
        self.state.threats[threat_id] = {**event.payload, "_ingested": event.timestamp}
        self.state.last_updated = datetime.now(timezone.utc).isoformat()
        logger.info("[MCE] Threat registered: %s", threat_id)

        # Tactical control measure: lethal response always requires human approval.
        if event.payload.get("lethal_response_requested"):
            await self._request_approval(
                action="LETHAL_ENGAGE",
                requestor=event.source_layer,
                payload=event.payload,
            )

    async def _on_asset_status(self, event: MCEvent) -> None:
        asset_id = event.payload.get("asset_id", event.event_id)
        self.state.assets[asset_id] = {**event.payload, "_ingested": event.timestamp}
        self.state.last_updated = datetime.now(timezone.utc).isoformat()

    async def _on_logistics(self, event: MCEvent) -> None:
        key = event.payload.get("category", "general")
        self.state.logistics[key] = {**event.payload, "_ingested": event.timestamp}
        self.state.last_updated = datetime.now(timezone.utc).isoformat()

    async def _on_task_order(self, event: MCEvent) -> None:
        task_id = event.payload.get("task_id", event.event_id)
        self.state.tasks[task_id] = {**event.payload, "status": "ISSUED"}
        self.state.last_updated = datetime.now(timezone.utc).isoformat()
        logger.info("[MCE] Task order issued: %s", task_id)

    # ── Human-in-the-loop ─────────────────────────────────────────────────────

    async def _request_approval(
        self,
        action: str,
        requestor: str,
        payload: Dict[str, Any],
    ) -> ApprovalState:
        ticket = self.gate.create_ticket(action, requestor, payload)
        loop = asyncio.get_running_loop()
        approval_event = MCEvent(
            EventType.APPROVAL_REQUEST,
            source_layer="mce",
            payload={"ticket_id": ticket.ticket_id, "action": action},
        )
        self.audit.append(approval_event, note=f"Awaiting human approval for {action}")
        await self.bus.publish(approval_event)
        state = await self.gate.await_approval(ticket, loop)
        result_type = (
            EventType.APPROVAL_GRANTED if state == ApprovalState.GRANTED else EventType.APPROVAL_DENIED
        )
        await self.bus.publish(MCEvent(result_type, "mce", {"ticket_id": ticket.ticket_id}))
        return state

    # ── Public API ────────────────────────────────────────────────────────────

    async def ingest(self, event: MCEvent) -> None:
        """Accept an event from any layer."""
        if not isinstance(event.payload, dict):
            raise ValueError("event payload must be a dictionary")
        if not event.source_layer or not isinstance(event.source_layer, str):
            raise ValueError("source_layer must be a non-empty string")
        self.audit.append(event, note="ingested")
        await self._queue.put(event)

    async def resolve_approval(
        self,
        ticket_id: str,
        granted: bool,
        resolver: str,
    ) -> Optional[ApprovalTicket]:
        if not ticket_id.strip() or not resolver.strip():
            return None
        return self.gate.resolve(ticket_id, granted, resolver)

    def get_cop_snapshot(self) -> Dict[str, Any]:
        return {
            "assets": dict(self.state.assets),
            "threats": dict(self.state.threats),
            "tasks": dict(self.state.tasks),
            "logistics": dict(self.state.logistics),
            "last_updated": self.state.last_updated,
            "pending_approvals": [asdict(ticket) for ticket in self.gate.get_pending()],
        }

    async def start(self) -> None:
        """Main event-loop pump. Run with asyncio.run(mce.start())."""
        self._running = True
        logger.info("[MCE] Mission Command Engine started.")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self.bus.publish(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        self._running = False
