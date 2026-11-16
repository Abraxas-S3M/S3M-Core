"""Collective Immunity: privacy-preserving learning across tenants (capability 15, research prototype).

Military/tactical context:
Every tenant learns slowly from its own incidents; small tenants barely learn at all. The
collective can learn faster, but raw logs must never be shared and no tenant should be able
to tell what happened at another. This prototype learns one thing well: per service class,
how often a reviewed attack attempt succeeded (the quantity CyberTwin calibration needs).

Protocol per round:
1. **Eligibility:** only analyst-reviewed incidents of opted-in tenants; raw logs never leave.
   Each tenant reduces them to a count vector ``[attempts_c, successes_c]`` with at most
   ``cap`` incidents per class per round (bounds one tenant's influence).
2. **Distributed differential privacy:** each tenant adds Gaussian noise ``N(0, sigma^2 / n)``
   per coordinate, so the sum carries ``N(0, sigma^2)`` without trusting the aggregator.
   Unit: one incident (L2 sensitivity sqrt(2)); ``sigma = z * sqrt(2)``. Privacy is accounted
   with Renyi DP: ``eps(delta) = min_a [T a / (2 z^2) + log(1/delta) / (a - 1)]``.
3. **Secure aggregation:** pairwise masks from X25519 key agreement and HKDF, added mod 2^32
   in fixed point. The aggregator sees only masked vectors; masks cancel in the sum. A
   missing participant aborts the round (dropout recovery by secret sharing is future work).
4. **Plausibility bound:** a sum outside ``[-slack, n * cap + slack]`` per class aborts the
   round (gross poisoning). Poisoning within the cap is not detectable under secure
   aggregation; its effect is bounded and measured.
5. **Use:** each tenant shrinks its local estimate toward the collective rate with strength
   ``m`` (Beta prior), so tenants with lots of data keep their own signal.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MOD = 2**32
SCALE = 1000  # fixed-point: 3 decimals


def rdp_epsilon(z: float, rounds: int, delta: float = 1e-6) -> float:
    if z <= 0:
        return math.inf
    return min(rounds * a / (2 * z * z) + math.log(1 / delta) / (a - 1) for a in np.arange(1.25, 256, 0.25))


@dataclass
class Incident:
    service: str
    succeeded: bool
    reviewed: bool = True


@dataclass
class Tenant:
    tenant_id: str
    opted_in: bool = True
    incidents: List[Incident] = field(default_factory=list)
    key: X25519PrivateKey = field(default_factory=X25519PrivateKey.generate)

    def counts(self, classes: Sequence[str], cap: int) -> np.ndarray:
        a = {c: 0 for c in classes}
        s = {c: 0 for c in classes}
        for inc in self.incidents:
            if not inc.reviewed or inc.service not in a or a[inc.service] >= cap:
                continue
            a[inc.service] += 1
            s[inc.service] += int(inc.succeeded)
        return np.array([a[c] for c in classes] + [s[c] for c in classes], dtype=float)


def _pair_mask(mine: X25519PrivateKey, theirs_pub, round_id: int, dim: int) -> np.ndarray:
    shared = mine.exchange(theirs_pub)
    seed = HKDF(hashes.SHA256(), 32, salt=round_id.to_bytes(8, "big"), info=b"s3m-immunity-mask").derive(shared)
    rng = np.random.default_rng(int.from_bytes(seed[:8], "big"))
    return rng.integers(0, MOD, size=dim, dtype=np.uint64)


def masked_contribution(t: Tenant, roster: Sequence[Tenant], vec: np.ndarray, round_id: int) -> np.ndarray:
    fixed = (np.round(vec * SCALE).astype(np.int64) % MOD).astype(np.uint64)
    out = fixed.copy()
    for other in roster:
        if other.tenant_id == t.tenant_id:
            continue
        m = _pair_mask(t.key, other.key.public_key(), round_id, len(vec))
        out = (out + m) % MOD if t.tenant_id < other.tenant_id else (out + MOD - m) % MOD
    return out


def unmask_sum(masked: Sequence[np.ndarray]) -> np.ndarray:
    total = np.zeros_like(masked[0])
    for m in masked:
        total = (total + m) % MOD
    signed = total.astype(np.int64)
    signed[signed >= MOD // 2] -= MOD
    return signed / SCALE


@dataclass
class RoundResult:
    round_id: int
    participants: List[str]
    aggregate: Optional[np.ndarray]
    status: str
    epsilon_spent: float


class Aggregator:
    """Sees masked vectors and the final sum only."""

    def __init__(self, classes: Sequence[str], *, cap: int = 30, z: float = 1.0, delta: float = 1e-6,
                 epsilon_budget: float = 8.0) -> None:
        self.classes = list(classes)
        self.cap = cap
        self.z = z
        self.delta = delta
        self.budget = epsilon_budget
        self.rounds = 0
        self.transcript: List[Dict[str, object]] = []
        self.seen_masked: List[np.ndarray] = []

    def run_round(self, tenants: Sequence[Tenant], *, seed: int = 0, drop: Optional[str] = None,
                  poison: Optional[Tuple[str, np.ndarray]] = None) -> RoundResult:
        roster = sorted([t for t in tenants if t.opted_in], key=lambda t: t.tenant_id)
        eps_next = rdp_epsilon(self.z, self.rounds + 1, self.delta)
        if eps_next > self.budget:
            return RoundResult(self.rounds, [], None, "REFUSED_PRIVACY_BUDGET", rdp_epsilon(self.z, self.rounds))
        n = len(roster)
        sigma = self.z * math.sqrt(2)
        rng = np.random.default_rng(seed)
        masked = []
        for t in roster:
            if t.tenant_id == drop:
                continue
            vec = t.counts(self.classes, self.cap) + rng.normal(0, sigma / math.sqrt(n), 2 * len(self.classes))
            if poison and poison[0] == t.tenant_id:
                vec = vec + poison[1]
            mv = masked_contribution(t, roster, vec, self.rounds)
            masked.append(mv)
            self.seen_masked.append(mv)
        if len(masked) != n:
            return RoundResult(self.rounds, [t.tenant_id for t in roster], None, "ABORTED_DROPOUT",
                               rdp_epsilon(self.z, self.rounds))
        agg = unmask_sum(masked)
        slack = 6 * sigma
        if (agg < -slack).any() or (agg > n * self.cap + slack).any():
            return RoundResult(self.rounds, [t.tenant_id for t in roster], None, "ABORTED_IMPLAUSIBLE",
                               rdp_epsilon(self.z, self.rounds))
        self.rounds += 1
        eps = rdp_epsilon(self.z, self.rounds, self.delta)
        self.transcript.append({"round": self.rounds, "participants": [t.tenant_id for t in roster],
                                "aggregate": [round(float(x), 3) for x in agg], "epsilon_cumulative": round(eps, 3)})
        return RoundResult(self.rounds, [t.tenant_id for t in roster], agg, "OK", eps)


def collective_rates(aggregates: Sequence[np.ndarray], k: int) -> np.ndarray:
    tot = np.sum(aggregates, axis=0)
    a, s = np.maximum(tot[:k], 1e-9), np.clip(tot[k:], 0, None)
    return np.clip(s / a, 0.001, 0.999)


def local_rates(counts: np.ndarray, k: int) -> np.ndarray:
    return (counts[k:] + 1) / (counts[:k] + 2)


def shrunk_rates(counts: np.ndarray, collective: np.ndarray, k: int, m: float = 20.0) -> np.ndarray:
    return (counts[k:] + m * collective) / (counts[:k] + m)


# ---- synthetic federation (for measurement) ---------------------------------------------------

CLASSES = ["https", "ssh", "smb", "rdp", "ldap", "kerberos", "postgres", "mssql", "rtsp", "ipp", "smtp"]


def synthetic_federation(*, n_tenants: int = 10, tau: float = 0.3, seed: int = 0, rounds: int = 4
                         ) -> Tuple[List[Tenant], Dict[str, np.ndarray], List[List[List[Incident]]]]:
    """Tenants with very different volumes; per-tenant truth deviates from a shared rate by ``tau`` (logit)."""
    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    base = nrng.beta(2, 5, len(CLASSES))
    volumes = [0.5, 1, 1, 2, 3, 5, 8, 12, 20, 30][:n_tenants]
    tenants, truth, per_round = [], {}, []
    for i in range(n_tenants):
        logit = np.log(base / (1 - base)) + nrng.normal(0, tau, len(CLASSES))
        truth[f"t{i:02d}"] = 1 / (1 + np.exp(-logit))
        tenants.append(Tenant(f"t{i:02d}"))
    for _ in range(rounds):
        batch = []
        for i, t in enumerate(tenants):
            incs = []
            for ci, c in enumerate(CLASSES):
                for _ in range(nrng.poisson(volumes[i])):
                    incs.append(Incident(c, rng.random() < truth[t.tenant_id][ci], reviewed=rng.random() < 0.9))
            batch.append(incs)
        per_round.append(batch)
    return tenants, truth, per_round


def evaluate(*, z: float, tau: float = 0.3, seed: int = 0, rounds: int = 4, cap: int = 30, m: float = 20.0
             ) -> Dict[str, object]:
    tenants, truth, per_round = synthetic_federation(tau=tau, seed=seed, rounds=rounds)
    k = len(CLASSES)
    agg = Aggregator(CLASSES, cap=cap, z=z, epsilon_budget=1e9)
    cum = {t.tenant_id: np.zeros(2 * k) for t in tenants}
    aggregates = []
    for r, batch in enumerate(per_round):
        for t, incs in zip(tenants, batch):
            t.incidents = incs
            cum[t.tenant_id] += t.counts(CLASSES, cap)
        res = agg.run_round(tenants, seed=seed * 100 + r)
        aggregates.append(res.aggregate)
    coll = collective_rates(aggregates, k)
    err_local, err_coll = {}, {}
    for t in tenants:
        tr = truth[t.tenant_id]
        err_local[t.tenant_id] = float(np.mean(np.abs(local_rates(cum[t.tenant_id], k) - tr)))
        err_coll[t.tenant_id] = float(np.mean(np.abs(shrunk_rates(cum[t.tenant_id], coll, k, m) - tr)))
    small = [t.tenant_id for t in tenants[:4]]
    large = [t.tenant_id for t in tenants[-3:]]
    return {"epsilon": round(rdp_epsilon(z, rounds), 3), "z": z,
            "mae_local_small": round(np.mean([err_local[x] for x in small]), 4),
            "mae_collective_small": round(np.mean([err_coll[x] for x in small]), 4),
            "mae_local_large": round(np.mean([err_local[x] for x in large]), 4),
            "mae_collective_large": round(np.mean([err_coll[x] for x in large]), 4)}


__all__ = ["Aggregator", "CLASSES", "Incident", "RoundResult", "Tenant", "collective_rates", "evaluate",
           "local_rates", "masked_contribution", "rdp_epsilon", "shrunk_rates", "synthetic_federation",
           "unmask_sum"]
