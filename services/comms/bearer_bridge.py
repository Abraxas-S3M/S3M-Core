"""
Bridge: BearerBroker -> Layer 08 RelayManager.
Replaces static relay fallback chain with bearer-scored routing.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.edge_runtime.bearer_broker import BearerBroker, LinkType, LinkState, MessageClass, RoutingDecision

logger = logging.getLogger("s3m.comms.bearer_bridge")

# Map Layer 08 relay backends to bearer link types
RELAY_TO_LINK: Dict[str, LinkType] = {
    "matrix": LinkType.WIRED,
    "xmpp": LinkType.WIRED,
    "rocket_chat": LinkType.WIRED,
    "meshtastic": LinkType.MESH,
    "p2p": LinkType.WIFI,
    "simulated": LinkType.WIFI,
}

# Map Layer 08 message priority to bearer message class
PRIORITY_TO_CLASS: Dict[str, MessageClass] = {
    "FLASH": MessageClass.URGENT_CONTROL,
    "IMMEDIATE": MessageClass.URGENT_CONTROL,
    "PRIORITY": MessageClass.SUMMARIES,
    "ROUTINE": MessageClass.TELEMETRY,
}

# Reverse: bearer link type -> preferred relay backend
LINK_TO_RELAY: Dict[LinkType, str] = {
    LinkType.WIRED: "matrix",
    LinkType.WIFI: "p2p",
    LinkType.MESH: "meshtastic",
    LinkType.CELLULAR: "xmpp",
    LinkType.SATELLITE: "xmpp",
}


class BearerRelayBridge:
    """
    Sits between CommsManager and RelayManager.
    CommsManager calls select_relay() instead of using the static fallback chain.
    """

    def __init__(self, broker: BearerBroker) -> None:
        self.broker = broker

    def select_relay(self, priority: str = "ROUTINE", payload_size_kb: float = 1.0) -> Dict[str, Any]:
        """
        Returns recommended relay backend and fallback order based on bearer scoring.
        """
        msg_class = PRIORITY_TO_CLASS.get(priority.upper(), MessageClass.TELEMETRY)
        decision: RoutingDecision = self.broker.route(msg_class, payload_size_kb)

        primary_relay = None
        if decision.selected_bearer:
            primary_relay = LINK_TO_RELAY.get(decision.selected_bearer, "simulated")

        fallback_relays = []
        for fallback in decision.fallback_bearers:
            relay = LINK_TO_RELAY.get(fallback)
            if relay and relay != primary_relay:
                fallback_relays.append(relay)

        # Always include simulated as ultimate fallback
        if "simulated" not in fallback_relays and primary_relay != "simulated":
            fallback_relays.append("simulated")

        return {
            "primary": primary_relay or "simulated",
            "fallbacks": fallback_relays,
            "persist_if_fail": decision.persist_if_fail,
            "compress": decision.compress,
            "delivery_mode": decision.delivery_mode.value,
            "reason": decision.reason,
        }

    def update_relay_health(self, relay_backend: str, is_up: bool, latency_ms: float = 100.0) -> None:
        """Called by RelayManager after each send attempt to feed bearer metrics."""
        link_type = RELAY_TO_LINK.get(relay_backend)
        if not link_type:
            return
        if is_up:
            self.broker.update_metrics(
                link_type,
                state=LinkState.UP,
                latency_ms=latency_ms,
                confidence=0.8,
            )
        else:
            self.broker.update_metrics(link_type, state=LinkState.DOWN, confidence=0.9)
