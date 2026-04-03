"""
Bearer broker for resilient multi-transport comms routing.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Callable, Dict, List, Optional


class LinkType(str, Enum):
    WIFI = "wifi"
    CELLULAR = "cellular"
    SATELLITE = "satellite"
    MESH = "mesh"
    LOCAL_RADIO_GATEWAY = "local_radio_gateway"
    WIRED = "wired"


class LinkState(str, Enum):
    UP = "up"
    DEGRADED = "degraded"
    INTERMITTENT = "intermittent"
    DOWN = "down"


class MessageClass(str, Enum):
    URGENT_CONTROL = "urgent_control"
    TELEMETRY = "telemetry"
    LOGS = "logs"
    SUMMARIES = "summaries"
    BULK_SYNC = "bulk_sync"
    MODEL_UPDATES = "model_updates"


class DeliveryMode(str, Enum):
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
    cost: float = 1.0
    confidence: float = 0.0
    power_draw_w: float = 0.0
    last_probed: float = field(default_factory=time.time)

    def composite_score(self) -> float:
        if self.state == LinkState.DOWN:
            return 99999.0
        return (
            (self.latency_ms / 100.0)
            + (self.packet_loss_pct * 5.0)
            + (self.cost * 2.0)
            + ((1.0 - max(0.0, min(1.0, self.confidence))) * 10.0)
        )


MESSAGE_ROUTING: Dict[MessageClass, Dict[str, Any]] = {
    MessageClass.URGENT_CONTROL: {
        "delivery_mode": DeliveryMode.REALTIME,
        "max_latency_ms": 2000,
        "max_size_kb": 4,
        "try_all_bearers": True,
        "compress": False,
    },
    MessageClass.TELEMETRY: {
        "delivery_mode": DeliveryMode.NEAR_REALTIME,
        "max_latency_ms": 10000,
        "max_size_kb": 64,
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.LOGS: {
        "delivery_mode": DeliveryMode.DELAY_TOLERANT,
        "max_latency_ms": 60000,
        "max_size_kb": 512,
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.SUMMARIES: {
        "delivery_mode": DeliveryMode.NEAR_REALTIME,
        "max_latency_ms": 30000,
        "max_size_kb": 128,
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.BULK_SYNC: {
        "delivery_mode": DeliveryMode.OPPORTUNISTIC,
        "max_latency_ms": None,
        "max_size_kb": None,
        "try_all_bearers": False,
        "compress": True,
    },
    MessageClass.MODEL_UPDATES: {
        "delivery_mode": DeliveryMode.DELAY_TOLERANT,
        "max_latency_ms": None,
        "max_size_kb": None,
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

    def to_dict(self) -> Dict[str, object]:
        return {
            "message_class": self.message_class.value,
            "selected_bearer": self.selected_bearer.value if self.selected_bearer else None,
            "fallback_bearers": [link.value for link in self.fallback_bearers],
            "delivery_mode": self.delivery_mode.value,
            "compress": self.compress,
            "persist_if_fail": self.persist_if_fail,
            "reason": self.reason,
        }


class BearerBroker:
    """Scores links and emits bearer decisions for tactical message classes."""

    def __init__(self, on_link_change: Optional[Callable[[bool], None]] = None) -> None:
        self._bearers: Dict[LinkType, LinkMetrics] = {}
        self._on_link_change = on_link_change
        self._any_bearer_up = False

    def register_bearer(self, link_type: LinkType, metrics: LinkMetrics) -> None:
        self._bearers[link_type] = metrics
        self._check_overall_state()

    def update_metrics(self, link_type: LinkType, **kwargs: Any) -> None:
        metrics = self._bearers.get(link_type)
        if metrics is None:
            metrics = LinkMetrics(link_type=link_type, state=LinkState.DOWN)
            self._bearers[link_type] = metrics
        for key, value in kwargs.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)
        metrics.last_probed = time.time()
        self._check_overall_state()

    def mark_down(self, link_type: LinkType) -> None:
        self.update_metrics(link_type, state=LinkState.DOWN)

    def mark_up(self, link_type: LinkType, latency_ms: float) -> None:
        self.update_metrics(link_type, state=LinkState.UP, latency_ms=latency_ms)

    def route(self, message_class: MessageClass, payload_size_kb: float = 0) -> RoutingDecision:
        policy = MESSAGE_ROUTING[message_class]
        delivery_mode: DeliveryMode = policy["delivery_mode"]
        available = [
            metrics
            for metrics in self._bearers.values()
            if metrics.state in {LinkState.UP, LinkState.DEGRADED}
        ]

        if not available:
            return RoutingDecision(
                message_class=message_class,
                selected_bearer=None,
                fallback_bearers=[],
                delivery_mode=delivery_mode,
                compress=bool(policy["compress"]),
                persist_if_fail=True,
                reason="No available bearers; queue for delayed delivery.",
            )

        max_size_kb = policy["max_size_kb"]
        if max_size_kb is not None and payload_size_kb > max_size_kb:
            return RoutingDecision(
                message_class=message_class,
                selected_bearer=None,
                fallback_bearers=[],
                delivery_mode=DeliveryMode.DELAY_TOLERANT,
                compress=True,
                persist_if_fail=True,
                reason="Payload exceeds tactical class size policy; persist for staged transfer.",
            )

        ranked = sorted(available, key=lambda metrics: metrics.composite_score())

        if message_class == MessageClass.URGENT_CONTROL and bool(policy["try_all_bearers"]):
            primary = ranked[0]
            fallback = [metrics.link_type for metrics in ranked[1:]]
            return RoutingDecision(
                message_class=message_class,
                selected_bearer=primary.link_type,
                fallback_bearers=fallback,
                delivery_mode=delivery_mode,
                compress=bool(policy["compress"]),
                persist_if_fail=False,
                reason="Urgent control message fans out across all healthy bearers.",
            )

        if message_class in {MessageClass.BULK_SYNC, MessageClass.MODEL_UPDATES}:
            high_bw = [metrics for metrics in ranked if metrics.bandwidth_kbps >= 256.0]
            if not high_bw:
                return RoutingDecision(
                    message_class=message_class,
                    selected_bearer=None,
                    fallback_bearers=[],
                    delivery_mode=DeliveryMode.OPPORTUNISTIC,
                    compress=bool(policy["compress"]),
                    persist_if_fail=True,
                    reason="No bearer meets minimum bandwidth for bulk/model transfer.",
                )
            ranked = high_bw

        primary = ranked[0]
        fallbacks = [metrics.link_type for metrics in ranked[1:3]]
        persist = delivery_mode in {DeliveryMode.DELAY_TOLERANT, DeliveryMode.OPPORTUNISTIC}

        return RoutingDecision(
            message_class=message_class,
            selected_bearer=primary.link_type,
            fallback_bearers=fallbacks,
            delivery_mode=delivery_mode,
            compress=bool(policy["compress"]),
            persist_if_fail=persist,
            reason="Selected lowest composite-score bearer for message class.",
        )

    def bearer_status(self) -> List[Dict[str, object]]:
        now = time.time()
        output: List[Dict[str, object]] = []
        for metrics in sorted(self._bearers.values(), key=lambda item: item.composite_score()):
            output.append(
                {
                    "type": metrics.link_type.value,
                    "state": metrics.state.value,
                    "latency_ms": metrics.latency_ms,
                    "bandwidth_kbps": metrics.bandwidth_kbps,
                    "packet_loss_pct": metrics.packet_loss_pct,
                    "score": metrics.composite_score(),
                    "age_seconds": round(max(0.0, now - metrics.last_probed), 2),
                }
            )
        return output

    def any_bearer_up(self) -> bool:
        return self._any_bearer_up

    def _check_overall_state(self) -> None:
        previous = self._any_bearer_up
        self._any_bearer_up = any(
            metrics.state in {LinkState.UP, LinkState.DEGRADED}
            for metrics in self._bearers.values()
        )
        if self._on_link_change and previous != self._any_bearer_up:
            self._on_link_change(self._any_bearer_up)
