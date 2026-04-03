#!/usr/bin/env python3
"""Unit tests for edge bearer broker routing logic."""

from __future__ import annotations

import pytest

from src.edge_runtime.bearer_broker import (
    BearerBroker,
    DeliveryMode,
    LinkMetrics,
    LinkState,
    LinkType,
    MessageClass,
    RoutingDecision,
)


def _mk(
    link_type: LinkType,
    *,
    state: LinkState = LinkState.UP,
    latency_ms: float = 100.0,
    loss: float = 0.0,
    bw: float = 512.0,
    confidence: float = 1.0,
    cost: float = 1.0,
) -> LinkMetrics:
    return LinkMetrics(
        link_type=link_type,
        state=state,
        latency_ms=latency_ms,
        packet_loss_pct=loss,
        bandwidth_kbps=bw,
        confidence=confidence,
        cost=cost,
    )


def test_route_queues_when_no_bearers_available() -> None:
    broker = BearerBroker()
    decision = broker.route(MessageClass.LOGS)
    assert isinstance(decision, RoutingDecision)
    assert decision.selected_bearer is None
    assert decision.persist_if_fail is True
    assert "queued locally" in decision.reason


def test_urgent_control_uses_primary_and_all_fallbacks() -> None:
    broker = BearerBroker()
    broker.register_bearer(LinkType.WIFI, _mk(LinkType.WIFI, latency_ms=40))
    broker.register_bearer(LinkType.CELLULAR, _mk(LinkType.CELLULAR, latency_ms=90))
    broker.register_bearer(LinkType.SATELLITE, _mk(LinkType.SATELLITE, latency_ms=400))

    decision = broker.route(MessageClass.URGENT_CONTROL, payload_size_kb=1)

    assert decision.delivery_mode == DeliveryMode.REALTIME
    assert decision.selected_bearer == LinkType.WIFI
    assert decision.fallback_bearers == [LinkType.CELLULAR, LinkType.SATELLITE]
    assert decision.persist_if_fail is True


def test_bulk_transfer_defers_without_high_bandwidth() -> None:
    broker = BearerBroker()
    broker.register_bearer(LinkType.WIFI, _mk(LinkType.WIFI, bw=128))
    broker.register_bearer(LinkType.CELLULAR, _mk(LinkType.CELLULAR, bw=200))

    decision = broker.route(MessageClass.BULK_SYNC, payload_size_kb=2048)

    assert decision.selected_bearer is None
    assert decision.delivery_mode == DeliveryMode.OPPORTUNISTIC
    assert "deferred" in decision.reason


def test_bulk_transfer_selects_best_high_bandwidth_link() -> None:
    broker = BearerBroker()
    broker.register_bearer(LinkType.WIFI, _mk(LinkType.WIFI, bw=1024, latency_ms=25))
    broker.register_bearer(LinkType.WIRED, _mk(LinkType.WIRED, bw=2048, latency_ms=35))
    broker.register_bearer(LinkType.CELLULAR, _mk(LinkType.CELLULAR, bw=300, latency_ms=100))

    decision = broker.route(MessageClass.MODEL_UPDATES, payload_size_kb=4096)

    assert decision.selected_bearer == LinkType.WIFI
    assert set(decision.fallback_bearers) == {LinkType.WIRED, LinkType.CELLULAR}
    assert decision.persist_if_fail is True


def test_default_route_prefers_lowest_composite_score() -> None:
    broker = BearerBroker()
    broker.register_bearer(
        LinkType.WIFI,
        _mk(LinkType.WIFI, latency_ms=80, loss=3.0, confidence=0.9, cost=2.0),
    )
    broker.register_bearer(
        LinkType.CELLULAR,
        _mk(LinkType.CELLULAR, latency_ms=120, loss=0.1, confidence=0.95, cost=1.0),
    )
    broker.register_bearer(
        LinkType.SATELLITE,
        _mk(LinkType.SATELLITE, latency_ms=800, loss=0.2, confidence=1.0, cost=5.0),
    )

    decision = broker.route(MessageClass.TELEMETRY, payload_size_kb=8)

    assert decision.selected_bearer == LinkType.CELLULAR
    assert decision.delivery_mode == DeliveryMode.NEAR_REALTIME
    assert decision.compress is True
    assert decision.persist_if_fail is True


def test_on_link_change_callback_fires_on_state_transition() -> None:
    transitions: list[bool] = []
    broker = BearerBroker(on_link_change=transitions.append)

    broker.register_bearer(LinkType.MESH, _mk(LinkType.MESH, state=LinkState.DOWN))
    assert transitions == []

    broker.mark_up(LinkType.MESH, latency_ms=140)
    assert transitions == [True]
    assert broker.any_bearer_up() is True

    broker.mark_down(LinkType.MESH)
    assert transitions == [True, False]
    assert broker.any_bearer_up() is False


def test_bearer_status_contains_observability_fields() -> None:
    broker = BearerBroker()
    broker.register_bearer(LinkType.WIFI, _mk(LinkType.WIFI, latency_ms=33, bw=900))
    status = broker.bearer_status()

    assert len(status) == 1
    entry = status[0]
    assert entry["type"] == "wifi"
    assert entry["state"] == "up"
    assert entry["latency_ms"] == 33
    assert entry["bandwidth_kbps"] == 900
    assert "score" in entry
    assert "age_sec" in entry


def test_invalid_inputs_raise_validation_errors() -> None:
    broker = BearerBroker()
    with pytest.raises(TypeError):
        broker.route("logs")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        broker.route(MessageClass.LOGS, payload_size_kb=-1)
    with pytest.raises(TypeError):
        broker.update_metrics("wifi", latency_ms=10)  # type: ignore[arg-type]
