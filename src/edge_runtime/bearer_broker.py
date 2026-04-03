"""
Transport-agnostic bearer broker.
Continuously scores all available bearers and routes each message
class over the optimal transport.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("s3m.edge_runtime.bearer_broker")


class LinkType(Enum):
    WIFI = "wifi"
    CELLULAR = "cellular"
    SATELLITE = "satellite"
    MESH = "mesh"  # Meshtastic / LoRa tactical mesh fallback
    LOCAL_RADIO_GATEWAY = "local_radio_gateway"
    WIRED = "wired"


class LinkState(Enum):
    UP = "up"
    DEGRADED = "degraded"
    INTERMITTENT = "intermittent"
    DOWN = "down"


class MessageClass(Enum):
    URGENT_CONTROL = "urgent_control"  # alerts, C2 commands
    TELEMETRY = "telemetry"  # periodic sensor data
    LOGS = "logs"  # operational logs
    SUMMARIES = "summaries"  # SITREPs, compressed intel
    BULK_SYNC = "bulk_sync"  # model artifacts, large logs
    MODEL_UPDATES = "model_updates"  # weight pushes


class DeliveryMode(Enum):
    REALTIME = "realtime"
    NEAR_REALTIME = "near_realtime"
    DELAY_TOLERANT = "delay_tolerant"
    OPPORTUNISTIC = "opportunistic"


@dataclass
class LinkMetrics:
    link_type: LinkType
    state: LinkState
    latency_ms: float = 9999.0
    jitter_ms: float = 9999.0
    packet_loss_pct: float = 100.0
    bandwidth_kbps: float = 0.0
    cost: float = 1.0  # relative cost (1=cheap, 10=expensive)
    confidence: float = 0.0  # 0-1, how reliable is this measurement
    power_draw_w: float = 0.0
    last_probed: float = field(default_factory=time.time)

    def composite_score(self) -> float:
        """Lower is better. Weighted composite for routing decisions."""
        if self.state == LinkState.DOWN:
            return 99999.0
        latency_factor = self.latency_ms / 100.0
        loss_factor = self.packet_loss_pct * 5.0
        cost_factor = self.cost * 2.0
        confidence_bonus = (1.0 - self.confidence) * 10.0
        return latency_factor + loss_factor + cost_factor + confidence_bonus


# Routing policy: message class -> delivery requirements.
MESSAGE_ROUTING: Dict[MessageClass, Dict[str, Any]] = {
    MessageClass.URGENT_CONTROL: {
        "delivery": DeliveryMode.REALTIME,
        "max_latency_ms": 2000,
        "max_size_kb": 4,
        "try_all_bearers": True,
        "compress": False,
    },
    MessageClass.TELEMETRY: {
        "delivery": DeliveryMode.NEAR_REALTIME,
        "max_latency_ms": 10000,
        "max_size_kb": 64,
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.LOGS: {
        "delivery": DeliveryMode.DELAY_TOLERANT,
        "max_latency_ms": 60000,
        "max_size_kb": 512,
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.SUMMARIES: {
        "delivery": DeliveryMode.NEAR_REALTIME,
        "max_latency_ms": 30000,
        "max_size_kb": 128,
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.BULK_SYNC: {
        "delivery": DeliveryMode.OPPORTUNISTIC,
        "max_latency_ms": 0,  # no deadline
        "max_size_kb": 0,  # unlimited
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.MODEL_UPDATES: {
        "delivery": DeliveryMode.DELAY_TOLERANT,
        "max_latency_ms": 0,
        "max_size_kb": 0,
        "try_all_bearers": False,
        "compress": True,
    },
}


@dataclass
class RoutingDecision:
    message_class: MessageClass
    selected_bearer: Optional[LinkType]
    fallback_bearers: List[LinkType]
    delivery_mode: DeliveryMode
    compress: bool
    persist_if_fail: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_class": self.message_class.value,
            "selected_bearer": self.selected_bearer.value if self.selected_bearer else None,
            "fallbacks": [b.value for b in self.fallback_bearers],
            "delivery_mode": self.delivery_mode.value,
            "compress": self.compress,
            "persist_if_fail": self.persist_if_fail,
            "reason": self.reason,
        }


class BearerBroker:
    """
    The routing brain in the communications layer.
    Sits above all relay adapters and continuously chooses the best
    transport per message class.
    """

    def __init__(self, on_link_change: Optional[Callable[[bool], None]] = None) -> None:
        self._bearers: Dict[LinkType, LinkMetrics] = {}
        self._on_link_change = on_link_change
        self._any_bearer_up = False

    # Bearer registration and probing
    def register_bearer(self, link_type: LinkType, metrics: LinkMetrics) -> None:
        if not isinstance(link_type, LinkType):
            raise TypeError("link_type must be a LinkType")
        if not isinstance(metrics, LinkMetrics):
            raise TypeError("metrics must be LinkMetrics")
        if metrics.link_type != link_type:
            raise ValueError("metrics.link_type must match link_type")
        self._bearers[link_type] = metrics
        self._check_overall_state()

    def update_metrics(self, link_type: LinkType, **kwargs: Any) -> None:
        if not isinstance(link_type, LinkType):
            raise TypeError("link_type must be a LinkType")
        if link_type not in self._bearers:
            self._bearers[link_type] = LinkMetrics(link_type=link_type, state=LinkState.DOWN)
        for k, v in kwargs.items():
            if hasattr(self._bearers[link_type], k):
                setattr(self._bearers[link_type], k, v)
        self._bearers[link_type].last_probed = time.time()
        self._check_overall_state()

    def mark_down(self, link_type: LinkType) -> None:
        if not isinstance(link_type, LinkType):
            raise TypeError("link_type must be a LinkType")
        if link_type in self._bearers:
            self._bearers[link_type].state = LinkState.DOWN
            self._check_overall_state()

    def mark_up(self, link_type: LinkType, latency_ms: float = 100.0) -> None:
        if not isinstance(link_type, LinkType):
            raise TypeError("link_type must be a LinkType")
        if latency_ms < 0:
            raise ValueError("latency_ms must be >= 0")
        if link_type in self._bearers:
            self._bearers[link_type].state = LinkState.UP
            self._bearers[link_type].latency_ms = latency_ms
            self._check_overall_state()

    # Route selection
    def route(self, message_class: MessageClass, payload_size_kb: float = 0) -> RoutingDecision:
        """Select the best bearer for a given message class."""
        if not isinstance(message_class, MessageClass):
            raise TypeError("message_class must be a MessageClass")
        if payload_size_kb < 0:
            raise ValueError("payload_size_kb must be >= 0")

        policy = MESSAGE_ROUTING.get(message_class, MESSAGE_ROUTING[MessageClass.LOGS])
        delivery = policy["delivery"]
        compress = policy["compress"]

        # Score all UP or DEGRADED bearers.
        available = [
            (lt, m)
            for lt, m in self._bearers.items()
            if m.state in (LinkState.UP, LinkState.DEGRADED)
        ]

        if not available:
            return RoutingDecision(
                message_class=message_class,
                selected_bearer=None,
                fallback_bearers=[],
                delivery_mode=delivery,
                compress=compress,
                persist_if_fail=True,
                reason="No bearers available; message will be queued locally.",
            )

        ranked = sorted(available, key=lambda pair: pair[1].composite_score())

        if policy.get("try_all_bearers"):
            selected = ranked[0][0]
            fallbacks = [lt for lt, _ in ranked[1:]]
            return RoutingDecision(
                message_class=message_class,
                selected_bearer=selected,
                fallback_bearers=fallbacks,
                delivery_mode=delivery,
                compress=compress,
                persist_if_fail=True,
                reason=f"Urgent: primary={selected.value}, all bearers attempted.",
            )

        # Bulk/model transfers only proceed on high-bandwidth links.
        if message_class in (MessageClass.BULK_SYNC, MessageClass.MODEL_UPDATES):
            high_bw = [(lt, m) for lt, m in ranked if m.bandwidth_kbps >= 256]
            if not high_bw:
                return RoutingDecision(
                    message_class=message_class,
                    selected_bearer=None,
                    fallback_bearers=[],
                    delivery_mode=DeliveryMode.OPPORTUNISTIC,
                    compress=True,
                    persist_if_fail=True,
                    reason="No high-bandwidth bearer; bulk transfer deferred.",
                )
            selected = high_bw[0][0]
            return RoutingDecision(
                message_class=message_class,
                selected_bearer=selected,
                fallback_bearers=[lt for lt, _ in high_bw[1:]],
                delivery_mode=delivery,
                compress=True,
                persist_if_fail=True,
                reason=f"Bulk: selected {selected.value} ({high_bw[0][1].bandwidth_kbps:.0f} kbps).",
            )

        selected = ranked[0][0]
        return RoutingDecision(
            message_class=message_class,
            selected_bearer=selected,
            fallback_bearers=[lt for lt, _ in ranked[1:3]],
            delivery_mode=delivery,
            compress=compress,
            persist_if_fail=(delivery != DeliveryMode.REALTIME),
            reason=f"Routed via {selected.value} (score={ranked[0][1].composite_score():.1f}).",
        )

    # Observability
    def bearer_status(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": lt.value,
                "state": m.state.value,
                "latency_ms": m.latency_ms,
                "bandwidth_kbps": m.bandwidth_kbps,
                "loss_pct": m.packet_loss_pct,
                "score": m.composite_score(),
                "age_sec": round(time.time() - m.last_probed, 1),
            }
            for lt, m in self._bearers.items()
        ]

    def any_bearer_up(self) -> bool:
        return self._any_bearer_up

    # Internal
    def _check_overall_state(self) -> None:
        was_up = self._any_bearer_up
        self._any_bearer_up = any(
            m.state in (LinkState.UP, LinkState.DEGRADED) for m in self._bearers.values()
        )
        if was_up != self._any_bearer_up and self._on_link_change:
            self._on_link_change(self._any_bearer_up)
