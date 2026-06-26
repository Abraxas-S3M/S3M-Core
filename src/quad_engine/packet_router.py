"""Packet classifier and router for the Quad-Engine Orchestration Layer.

Tactical context:
    Inbound operational packets are heterogeneous: a COP track update needs an
    immediate tactical summary, an alert needs threat reasoning first, and a
    decision request needs planning/COA work up front. The router inspects the
    packet type and payload, picks a *primary* engine plus *supporting* engines,
    and explains the choice in plain language for the audit trail.

    Routing here is deterministic and offline. It never calls a model; it only
    decides which advisory engines the orchestrator should consult. Human review
    remains mandatory regardless of the route chosen.
"""

from __future__ import annotations

from typing import Any, Dict

from src.quad_engine.models import (
    ARABIC_ENGINE,
    PLANNING_ENGINE,
    REASONING_ENGINE,
    TACTICAL_ENGINE,
    OperationalPacket,
    PacketType,
    RouteInfo,
)

# Map each canonical engine to the advisory route-hint vocabulary shared with
# the COP event bus (tactical / reasoning / planning / arabic_nlp).
_ROUTE_HINT_BY_ENGINE: Dict[str, str] = {
    TACTICAL_ENGINE: "tactical",
    REASONING_ENGINE: "reasoning",
    PLANNING_ENGINE: "planning",
    ARABIC_ENGINE: "arabic_nlp",
}

# Primary engine + ordered supporting engines per packet type.
_ROUTE_TABLE: Dict[PacketType, Dict[str, Any]] = {
    PacketType.TRACK_UPDATE: {
        "primary": TACTICAL_ENGINE,
        "supporting": [REASONING_ENGINE, PLANNING_ENGINE, ARABIC_ENGINE],
        "reason": (
            "Packet contains air/maritime COP event requiring tactical summary "
            "and commander recommendation."
        ),
    },
    PacketType.ALERT: {
        "primary": REASONING_ENGINE,
        "supporting": [TACTICAL_ENGINE, PLANNING_ENGINE, ARABIC_ENGINE],
        "reason": (
            "Alert packet requires threat assessment and competing-hypotheses "
            "reasoning before tactical and planning support."
        ),
    },
    PacketType.DECISION_REQUEST: {
        "primary": PLANNING_ENGINE,
        "supporting": [REASONING_ENGINE, TACTICAL_ENGINE, ARABIC_ENGINE],
        "reason": (
            "Decision request requires course-of-action options and watch "
            "priorities; routed to planning with reasoning support. Human "
            "review is mandatory before any decision is acted upon."
        ),
    },
    PacketType.FEED: {
        "primary": TACTICAL_ENGINE,
        "supporting": [REASONING_ENGINE, ARABIC_ENGINE],
        "reason": (
            "Feed message requires fast tactical summarization and Arabic "
            "commander phrasing support."
        ),
    },
    PacketType.OPERATOR_NOTE: {
        "primary": TACTICAL_ENGINE,
        "supporting": [REASONING_ENGINE, PLANNING_ENGINE, ARABIC_ENGINE],
        "reason": (
            "Operator note summarized tactically with reasoning and planning "
            "support for situational context."
        ),
    },
}


def _refine_reason(packet: OperationalPacket, base_reason: str) -> str:
    """Append payload-aware context to the routing rationale."""
    payload = packet.payload or {}
    affiliation = str(payload.get("affiliation", "")).lower()
    domain = str(payload.get("domain", "")).lower()
    extras = []
    if domain:
        extras.append(f"domain={domain}")
    if affiliation:
        extras.append(f"affiliation={affiliation}")
    if affiliation in {"hostile", "suspect", "unknown"}:
        extras.append("elevated reasoning priority due to non-friendly contact")
    if not extras:
        return base_reason
    return f"{base_reason} ({'; '.join(extras)})"


class PacketRouter:
    """Deterministic classifier/router for operational packets."""

    def classify(self, packet: OperationalPacket) -> PacketType:
        """Return the packet type, defaulting safely to a track update."""
        if isinstance(packet.packet_type, PacketType):
            return packet.packet_type
        try:
            return PacketType(str(packet.packet_type))
        except ValueError:
            return PacketType.TRACK_UPDATE

    def route(self, packet: OperationalPacket) -> RouteInfo:
        """Produce a :class:`RouteInfo` for the packet."""
        packet_type = self.classify(packet)
        spec = _ROUTE_TABLE.get(packet_type, _ROUTE_TABLE[PacketType.TRACK_UPDATE])
        primary = spec["primary"]
        return RouteInfo(
            primary_engine=primary,
            supporting_engines=list(spec["supporting"]),
            reason=_refine_reason(packet, spec["reason"]),
            route_hint=_ROUTE_HINT_BY_ENGINE.get(primary, "tactical"),
        )


_GLOBAL_ROUTER: PacketRouter = PacketRouter()


def get_packet_router() -> PacketRouter:
    """Return the shared packet router instance."""
    return _GLOBAL_ROUTER
