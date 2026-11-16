"""Representative, deterministic telemetry for the enterprise_200 range (contract v0.1).

Military/tactical context:
Cortex needs evidence of how the fabric is actually used before it narrows anything.
This generator produces the telemetry a control plane would stream - 5-minute flow
summaries per route, STLink heartbeats, SealedTunnel state - shaped by each route's
observed 30-day use and a diurnal duty cycle, plus one planted anomaly (CCTV cameras
probing the corporate user network over the flat legacy route) for detection drills.

Everything is synthetic and reproducible from (scenario, start, hours, seed).
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Mapping, Optional

WINDOW = 300
SCHEMA = "s3m.cortex.telemetry/0.1"
UDP_SERVICES = {"syslog", "ipsec", "rtsp"}


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_id(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _diurnal(ts: datetime) -> float:
    """Duty cycle: office hours peak (local UTC+3), quiet nights and weekends."""
    hour = (ts.hour + 3) % 24
    weekday = ts.weekday() < 5 or ts.weekday() == 6  # Sun-Thu working week
    base = 0.15 + 0.85 * max(0.0, math.sin(math.pi * (hour - 6) / 13)) if 6 <= hour <= 19 else 0.12
    return base if weekday else base * 0.3


def _envelope(etype: str, ts: datetime, component: str, tenant: str, attributes: Dict[str, Any],
              severity: str = "info", sandbox: Optional[str] = None) -> Dict[str, Any]:
    ev = {
        "schema": SCHEMA,
        "event_id": _event_id(etype, _iso(ts), component, sorted(attributes.items())),
        "type": etype,
        "time": _iso(ts),
        "source": {"system": "control-plane", "component": component},
        "tenant": tenant,
        "severity": severity,
        "attributes": attributes,
    }
    if sandbox:
        ev["sandbox"] = sandbox
    return ev


def generate(
    scenario: Mapping[str, Any],
    *,
    start: datetime,
    hours: float = 1.0,
    seed: int = 20261116,
    tenant: str = "range",
    anomaly_route: str = "rt-cams-corp",
) -> Iterator[Dict[str, Any]]:
    """Yield telemetry events in time order."""
    routes = [r for r in scenario.get("routes", []) if r.get("status", "active") != "expired"]
    stlinks = scenario.get("stlinks", [])
    windows = int(hours * 3600 // WINDOW)
    start = start.replace(second=0, microsecond=0, tzinfo=timezone.utc)
    anomaly_window = windows // 2
    for w in range(windows):
        ts = start + timedelta(seconds=w * WINDOW)
        duty = _diurnal(ts)
        for r in sorted(routes, key=lambda x: x["id"]):
            rng = random.Random(f"{seed}:{r['id']}:{w}")
            per_window = int(r.get("observed_sessions_30d", 0)) / (30 * 24 * 12)
            lam = per_window * duty / 0.35  # normalise so the 30-day mean holds
            sessions = int(rng.gauss(lam, math.sqrt(lam)) + 0.5) if lam > 0 else 0
            sessions = max(0, sessions)
            denied = 1 if rng.random() < 0.02 else 0
            if r["id"] == anomaly_route and w == anomaly_window:
                denied = 37
            attrs = {
                "s3m.route.id": r["id"],
                "s3m.window.start": _iso(ts),
                "s3m.window.seconds": WINDOW,
                "network.transport": "udp" if r.get("service") in UDP_SERVICES else "tcp",
                "server.port": int(r.get("port", 0)),
                "s3m.service": r.get("service", "any"),
                "s3m.sessions": sessions,
                "s3m.unique_sources": min(sessions, int(r.get("source_size", 1))),
                "s3m.bytes_in": sessions * rng.randint(2_000, 60_000),
                "s3m.bytes_out": sessions * rng.randint(4_000, 400_000),
                "s3m.denied_attempts": denied,
                "s3m.sealed_tunnel": bool(r.get("sealed_tunnel")),
            }
            yield _envelope("flow.summary", ts + timedelta(seconds=WINDOW), "flow-aggregator", tenant, attrs)
            if denied >= 20:
                yield _envelope(
                    "anomaly.flag", ts + timedelta(seconds=WINDOW), "flow-aggregator", tenant,
                    {"s3m.route.id": r["id"], "s3m.kind": "denied_spike", "s3m.score": 0.93,
                     "s3m.detail": f"{denied} denied attempts in 300s from {r['source']}"},
                    severity="warning",
                )
        for s in sorted(stlinks, key=lambda x: x["id"]):
            rng = random.Random(f"{seed}:{s['id']}:{w}")
            yield _envelope(
                "stlink.heartbeat", ts + timedelta(seconds=WINDOW), "stlink-monitor", tenant,
                {"s3m.stlink.id": s["id"], "s3m.status": s.get("status", "active"),
                 "s3m.latency_ms": round(rng.uniform(3.0, 18.0), 2),
                 "s3m.tunnels": sum(1 for r in routes if r.get("sealed_tunnel") and r.get("target") == s.get("host"))},
            )
        for r in sorted((x for x in routes if x.get("sealed_tunnel")), key=lambda x: x["id"]):
            yield _envelope(
                "tunnel.state", ts + timedelta(seconds=WINDOW), "tunnel-monitor", tenant,
                {"s3m.tunnel.id": "st-" + r["id"].removeprefix("rt-"), "s3m.route.id": r["id"],
                 "s3m.status": "up", "s3m.rekey_age_s": (w * WINDOW) % 3600},
            )


def tunnels_from_routes(routes: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"id": "st-" + r["id"].removeprefix("rt-"), "route_id": r["id"], "source": r["source"],
         "target": r["target"], "service": r["service"], "status": "up" if r.get("status") != "expired" else "down"}
        for r in routes if r.get("sealed_tunnel")
    ]
