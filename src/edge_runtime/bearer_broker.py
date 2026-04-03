"""Transport-agnostic bearer scoring for austere tactical networking."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Callable, Dict, List

logger = logging.getLogger("s3m.edge_runtime.bearer_broker")


class LinkType(str, Enum):
    WIFI = "wifi"
    CELLULAR = "cellular"
    SATELLITE = "satellite"
    MESH = "mesh"
    WIRED = "wired"


@dataclass(slots=True)
class LinkMetrics:
    link_type: LinkType
    latency_ms: float
    jitter_ms: float
    loss_percent: float
    bandwidth_mbps: float
    available: bool = True

    def composite_score(self) -> float:
        if not self.available:
            return 0.0
        # Keep routing deterministic and bounded for field safety-critical behavior.
        latency_factor = max(0.0, 1.0 - (self.latency_ms / 1000.0))
        jitter_factor = max(0.0, 1.0 - (self.jitter_ms / 200.0))
        loss_factor = max(0.0, 1.0 - (self.loss_percent / 100.0))
        bandwidth_factor = min(1.0, self.bandwidth_mbps / 100.0)
        return round(
            (0.35 * latency_factor)
            + (0.2 * jitter_factor)
            + (0.3 * loss_factor)
            + (0.15 * bandwidth_factor),
            4,
        )


class MessageClass(str, Enum):
    URGENT_CONTROL = "urgent_control"
    TELEMETRY = "telemetry"
    LOGS = "logs"
    SUMMARIES = "summaries"
    BULK_SYNC = "bulk_sync"
    MODEL_UPDATES = "model_updates"


@dataclass(slots=True, frozen=True)
class RoutingPolicy:
    preferred: List[LinkType]
    persist_if_fail: bool


MESSAGE_ROUTING: Dict[MessageClass, RoutingPolicy] = {
    MessageClass.URGENT_CONTROL: RoutingPolicy(
        preferred=[LinkType.WIRED, LinkType.MESH, LinkType.WIFI, LinkType.CELLULAR, LinkType.SATELLITE],
        persist_if_fail=True,
    ),
    MessageClass.TELEMETRY: RoutingPolicy(
        preferred=[LinkType.WIFI, LinkType.WIRED, LinkType.MESH, LinkType.CELLULAR, LinkType.SATELLITE],
        persist_if_fail=True,
    ),
    MessageClass.LOGS: RoutingPolicy(
        preferred=[LinkType.WIFI, LinkType.CELLULAR, LinkType.WIRED, LinkType.MESH, LinkType.SATELLITE],
        persist_if_fail=True,
    ),
    MessageClass.SUMMARIES: RoutingPolicy(
        preferred=[LinkType.CELLULAR, LinkType.WIFI, LinkType.SATELLITE, LinkType.MESH, LinkType.WIRED],
        persist_if_fail=True,
    ),
    MessageClass.BULK_SYNC: RoutingPolicy(
        preferred=[LinkType.WIRED, LinkType.WIFI, LinkType.CELLULAR, LinkType.SATELLITE, LinkType.MESH],
        persist_if_fail=True,
    ),
    MessageClass.MODEL_UPDATES: RoutingPolicy(
        preferred=[LinkType.WIRED, LinkType.WIFI, LinkType.CELLULAR, LinkType.SATELLITE, LinkType.MESH],
        persist_if_fail=True,
    ),
}


@dataclass(slots=True, frozen=True)
class RoutingDecision:
    selected_bearer: LinkType | None
    fallbacks: List[LinkType]
    persist_if_fail: bool
    score: float


class BearerBroker:
    """Scores available bearers and emits deterministic routing choices."""

    def __init__(self, on_link_change: Callable[[bool], None] | None = None) -> None:
        self._on_link_change = on_link_change
        self._links: Dict[LinkType, LinkMetrics] = {
            LinkType.WIFI: LinkMetrics(LinkType.WIFI, 30.0, 8.0, 1.0, 100.0, False),
            LinkType.CELLULAR: LinkMetrics(LinkType.CELLULAR, 90.0, 15.0, 2.5, 20.0, False),
            LinkType.SATELLITE: LinkMetrics(LinkType.SATELLITE, 650.0, 60.0, 5.0, 8.0, False),
            LinkType.MESH: LinkMetrics(LinkType.MESH, 120.0, 30.0, 4.0, 6.0, False),
            LinkType.WIRED: LinkMetrics(LinkType.WIRED, 10.0, 2.0, 0.2, 1000.0, False),
        }
        self._any_up = False

    def update_link(self, metrics: LinkMetrics) -> None:
        previous = self._any_up
        self._links[metrics.link_type] = metrics
        self._any_up = any(link.available for link in self._links.values())
        if self._on_link_change and previous != self._any_up:
            self._on_link_change(self._any_up)
        logger.info(
            "Link updated type=%s up=%s score=%.3f",
            metrics.link_type.value,
            metrics.available,
            metrics.composite_score(),
        )

    def route(self, message_class: MessageClass) -> RoutingDecision:
        policy = MESSAGE_ROUTING[message_class]
        ordered = sorted(
            policy.preferred,
            key=lambda lt: self._links[lt].composite_score(),
            reverse=True,
        )
        available = [lt for lt in ordered if self._links[lt].available]
        selected = available[0] if available else None
        fallbacks = available[1:] if len(available) > 1 else []
        score = self._links[selected].composite_score() if selected else 0.0
        return RoutingDecision(
            selected_bearer=selected,
            fallbacks=fallbacks,
            persist_if_fail=policy.persist_if_fail,
            score=score,
        )

    def link_snapshot(self) -> Dict[str, Dict[str, float | bool | str]]:
        return {
            lt.value: {
                "available": metrics.available,
                "latency_ms": metrics.latency_ms,
                "jitter_ms": metrics.jitter_ms,
                "loss_percent": metrics.loss_percent,
                "bandwidth_mbps": metrics.bandwidth_mbps,
                "score": metrics.composite_score(),
            }
            for lt, metrics in self._links.items()
        }
