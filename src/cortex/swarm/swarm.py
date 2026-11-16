"""Sovereign CyberSwarm: isolated regional Cortex deployments sharing minimal signed summaries (capability 14).

Military/tactical context:
Regions analyse locally and keep their data. What crosses a boundary is a *threat summary*:
a technique, a keyed hash of an indicator (comparable only by regions holding the community
key), a severity and a bucketed count. Every summary passes the origin's release guard and
the recipient's admission check; links may be cut for days and resume in order.

Release guard (outbound, per region):
- field whitelist (no free text, no host names, addresses, users, raw indicators);
- content scan of every value for addresses, inventory names and raw-indicator leakage;
- k-anonymity: at least ``k`` independent local observations;
- recipient must be a configured partner whose clearance covers the classification;
- classifications listed in ``human_release`` need a release officer's approval;
- per-recipient rate limit.

Admission (inbound): signature by the origin's registered key, intended recipient, TTL,
replay cache, schema, and a partner relationship. Store-and-forward links queue across
partitions and deliver in order when they come back; expired summaries are dropped.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Deque, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def canonical(d: Mapping[str, Any]) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str).encode()


def indicator_hmac(community_key: bytes, indicator: str) -> str:
    return hmac.new(community_key, indicator.strip().lower().encode(), hashlib.sha256).hexdigest()[:32]


@dataclass
class Summary:
    summary_id: str
    origin: str
    recipients: List[str]
    issued_at: str
    ttl_hours: int
    kind: str
    technique: str
    indicator_hmac: str
    severity: str
    confidence: float
    observations_bucket: str
    classification: str
    recommended_capability: str

    def body(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Envelope:
    summary: Dict[str, Any]
    signature: str  # hex Ed25519 over canonical(summary)


@dataclass
class Decision:
    ok: bool
    reasons: List[str] = field(default_factory=list)


def bucket(n: int) -> str:
    return "3-9" if n < 10 else ("10-99" if n < 100 else "100+")


class Region:
    def __init__(self, region_id: str, policy: Mapping[str, Any], community_key: bytes, *,
                 inventory_names: Sequence[str] = (), clock: Callable[[], datetime]) -> None:
        self.region_id = region_id
        self.policy = policy
        self.community_key = community_key
        self.key = Ed25519PrivateKey.generate()
        self.public_key = self.key.public_key()
        self.inventory_names = {n.lower() for n in inventory_names}
        self.clock = clock
        self.trust: Dict[str, Ed25519PublicKey] = {}
        self.seen: Set[str] = set()
        self.inbox: List[Dict[str, Any]] = []
        self.rejected: List[Tuple[str, List[str]]] = []
        self.released: List[str] = []
        self.blocked: List[Tuple[str, List[str]]] = []
        self.local_indicators: Dict[str, str] = {}  # raw indicator -> where seen (never leaves)
        self._sent: Dict[str, Deque[datetime]] = {}
        self._n = 0

    # ---- outbound ---------------------------------------------------------------------------
    def draft(self, *, kind: str, technique: str, indicator: str, observations: int, severity: str,
              confidence: float, classification: str, recipients: Sequence[str], capability: str,
              ttl_hours: int = 72) -> Tuple[Summary, int]:
        self._n += 1
        return Summary(f"{self.region_id}-{self._n:05d}", self.region_id, list(recipients),
                       self.clock().isoformat(), ttl_hours, kind, technique,
                       indicator_hmac(self.community_key, indicator), severity, round(confidence, 2),
                       bucket(observations), classification, capability), observations

    def guard(self, s: Summary, observations: int, *, release_officer: bool = False,
              raw_indicators: Sequence[str] = ()) -> Decision:
        pol, reasons = self.policy, []
        body = s.body()
        extra = set(body) - set(pol["summary_fields"])
        if extra:
            reasons.append(f"fields not allowed: {sorted(extra)}")
        if s.kind not in pol["kinds"]:
            reasons.append(f"kind {s.kind} not allowed")
        text = " ".join(str(v) for k, v in body.items() if k not in ("indicator_hmac", "summary_id", "issued_at"))
        if IPV4.search(text):
            reasons.append("address in summary")
        low = text.lower()
        leaked = sorted(n for n in self.inventory_names if n and re.search(rf"\b{re.escape(n)}\b", low))
        if leaked:
            reasons.append(f"inventory names in summary: {leaked[:3]}")
        if any(r and r.lower() in low for r in list(raw_indicators) + list(self.local_indicators)):
            reasons.append("raw indicator in summary")
        if observations < int(pol["k_anonymity"]):
            reasons.append(f"k-anonymity: {observations} < {pol['k_anonymity']}")
        order = pol["classification_order"]
        me = pol["regions"][self.region_id]
        if s.classification not in order or order.index(me["clearance"]) < order.index(s.classification):
            reasons.append(f"origin not cleared for {s.classification}")
        for r in s.recipients:
            rp = pol["regions"].get(r)
            if rp is None or r not in me["partners"]:
                reasons.append(f"{r} is not a partner")
            elif order.index(rp["clearance"]) < order.index(s.classification):
                reasons.append(f"{r} not cleared for {s.classification}")
        if s.classification in pol["human_release"] and not release_officer:
            reasons.append(f"{s.classification} needs a release officer")
        now = self.clock()
        for r in s.recipients:
            q = self._sent.setdefault(r, deque())
            while q and q[0] < now - timedelta(hours=1):
                q.popleft()
            if len(q) >= int(pol["max_per_hour"]):
                reasons.append(f"rate limit to {r}")
        return Decision(not reasons, reasons)

    def release(self, s: Summary, observations: int, **kw) -> Optional[Envelope]:
        d = self.guard(s, observations, **kw)
        if not d.ok:
            self.blocked.append((s.summary_id, d.reasons))
            return None
        for r in s.recipients:
            self._sent.setdefault(r, deque()).append(self.clock())
        self.released.append(s.summary_id)
        body = s.body()
        return Envelope(body, self.key.sign(canonical(body)).hex())

    # ---- inbound ----------------------------------------------------------------------------
    def admit(self, env: Envelope) -> Decision:
        s, reasons = env.summary, []
        origin = s.get("origin")
        pk = self.trust.get(str(origin))
        if pk is None:
            reasons.append(f"unknown origin {origin}")
        else:
            try:
                pk.verify(bytes.fromhex(env.signature), canonical(s))
            except (InvalidSignature, ValueError):
                reasons.append("bad signature")
        if self.region_id not in s.get("recipients", []):
            reasons.append("not an intended recipient")
        if origin not in self.policy["regions"].get(self.region_id, {}).get("partners", []):
            reasons.append("origin is not a partner")
        if set(s) - set(self.policy["summary_fields"]):
            reasons.append("schema violation")
        try:
            issued = datetime.fromisoformat(s["issued_at"])
            if self.clock() > issued + timedelta(hours=int(s["ttl_hours"])):
                reasons.append("expired")
        except (KeyError, ValueError):
            reasons.append("bad timestamp")
        if s.get("summary_id") in self.seen:
            reasons.append("replay")
        d = Decision(not reasons, reasons)
        if d.ok:
            self.seen.add(s["summary_id"])
            self.inbox.append(dict(s))
        else:
            self.rejected.append((str(s.get("summary_id")), reasons))
        return d

    def matches(self) -> List[Dict[str, Any]]:
        """Received indicators that match local observations (compared by keyed hash only)."""
        local = {indicator_hmac(self.community_key, i): where for i, where in self.local_indicators.items()}
        return [dict(s, local_match=local[s["indicator_hmac"]]) for s in self.inbox if s["indicator_hmac"] in local]


class SwarmNetwork:
    """Store-and-forward links between isolated regions; partitions queue, not drop."""

    def __init__(self, regions: Sequence[Region]) -> None:
        self.regions = {r.region_id: r for r in regions}
        for r in regions:
            for o in regions:
                if o is not r:
                    r.trust[o.region_id] = o.public_key
        self.up: Dict[Tuple[str, str], bool] = {}
        self.queues: Dict[Tuple[str, str], Deque[Envelope]] = {}

    def set_link(self, a: str, b: str, up: bool) -> None:
        self.up[(a, b)] = self.up[(b, a)] = up

    def send(self, env: Envelope) -> None:
        for r in env.summary["recipients"]:
            self.queues.setdefault((env.summary["origin"], r), deque()).append(env)

    def deliver(self) -> Dict[str, List[Decision]]:
        out: Dict[str, List[Decision]] = {}
        for (a, b), q in self.queues.items():
            if not self.up.get((a, b), True):
                continue
            while q:
                out.setdefault(b, []).append(self.regions[b].admit(q.popleft()))
        return out


def cross_region_value(origin_game, partner_game, campaign, *, lag_hours: int = 24, release_hours: int = 2,
                       hunt_factor: float = 5.0, runs: int = 150, seed: int = 1,
                       playbook: str = "quarantine_detected") -> Dict[str, Any]:
    """The same adversary reaches the partner ``lag_hours`` after the origin. With the swarm,
    the origin's first detection becomes a summary ``release_hours`` later and the partner hunts
    for the indicator (detection x ``hunt_factor``) from then on. Same draws with and without."""
    origin = origin_game.compare(campaign, runs=runs, seed=seed)[playbook]
    boosts = [None if d is None else (max(0, d + release_hours - lag_hours), hunt_factor) for d in origin.detected_at]
    without = partner_game.compare(campaign, runs=runs, seed=seed + 101)[playbook]
    with_ = partner_game.compare(campaign, runs=runs, seed=seed + 101, boosts=boosts)[playbook]
    return {"partner_assets_lost_without": round(without.mean_assets_lost, 3),
            "partner_assets_lost_with": round(with_.mean_assets_lost, 3),
            "origin_detected": sum(d is not None for d in origin.detected_at) / runs,
            "losses_without": without.losses, "losses_with": with_.losses}


__all__ = ["cross_region_value", "Decision", "Envelope", "Region", "Summary", "SwarmNetwork", "bucket", "canonical", "indicator_hmac"]

