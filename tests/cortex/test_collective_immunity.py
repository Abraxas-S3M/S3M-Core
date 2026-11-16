"""Collective Immunity: learn across tenants without sharing raw data (research prototype).

Military/tactical context:
The aggregator must learn the sum and nothing else; one incident must have a bounded,
accounted effect; gross poisoning and dropouts must abort a round; and the benefit must be
reported for the tenants it helps and the ones it does not.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.cortex.immunity.federated import (
    CLASSES,
    MOD,
    Aggregator,
    Incident,
    Tenant,
    collective_rates,
    evaluate,
    masked_contribution,
    rdp_epsilon,
    unmask_sum,
)

pytestmark = pytest.mark.cortex
K = len(CLASSES)


def _tenants(n=5, per_class=6, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        incs = [Incident(c, bool(rng.random() < 0.3)) for c in CLASSES for _ in range(per_class)]
        out.append(Tenant(f"t{i}", incidents=incs))
    return out


def test_masks_cancel_exactly_and_hide_each_vector() -> None:
    ts = _tenants()
    vecs = [t.counts(CLASSES, 30) for t in ts]
    masked = [masked_contribution(t, ts, v, round_id=3) for t, v in zip(ts, vecs)]
    assert np.allclose(unmask_sum(masked), np.sum(vecs, axis=0))
    m = masked[0].astype(float)
    assert abs(np.corrcoef(m, vecs[0])[0, 1]) < 0.5 and 0.2 * MOD < m.mean() < 0.8 * MOD  # looks uniform
    assert not np.array_equal(masked_contribution(ts[0], ts, vecs[0], 3), masked_contribution(ts[0], ts, vecs[0], 4))


def test_only_reviewed_opted_in_capped_data_counts() -> None:
    t = Tenant("t0", incidents=[Incident("ssh", True)] * 40 + [Incident("ssh", True, reviewed=False)] * 10)
    v = t.counts(CLASSES, cap=30)
    assert v[CLASSES.index("ssh")] == 30 and v[K + CLASSES.index("ssh")] == 30
    ts = _tenants(4)
    ts[2].opted_in = False
    res = Aggregator(CLASSES, z=2.0).run_round(ts)
    assert res.status == "OK" and "t2" not in res.participants


def test_round_aborts_on_dropout_and_gross_poisoning() -> None:
    ts = _tenants(4)
    assert Aggregator(CLASSES, z=2.0).run_round(ts, drop="t1").status == "ABORTED_DROPOUT"
    huge = np.zeros(2 * K)
    huge[K] = 10_000  # claims 10,000 successes on one class
    assert Aggregator(CLASSES, z=2.0).run_round(ts, poison=("t3", huge)).status == "ABORTED_IMPLAUSIBLE"


def test_poisoning_within_the_cap_has_bounded_effect() -> None:
    ts = _tenants(8, per_class=10)
    clean = Aggregator(CLASSES, z=0.5, epsilon_budget=1e9).run_round(ts, seed=1).aggregate
    sneaky = np.zeros(2 * K)
    sneaky[K:] = 10  # one tenant reports all its attempts as successes (stays within the cap)
    dirty = Aggregator(CLASSES, z=0.5, epsilon_budget=1e9).run_round(ts, seed=1, poison=("t0", sneaky)).aggregate
    shift = np.abs(collective_rates([dirty], K) - collective_rates([clean], K))
    assert shift.max() <= 10 / 80 + 0.02  # at most one tenant's share of the attempts


def test_privacy_accounting_and_budget() -> None:
    assert rdp_epsilon(2.0, 1) < rdp_epsilon(2.0, 4) < rdp_epsilon(2.0, 8)
    assert rdp_epsilon(4.0, 4) < rdp_epsilon(2.0, 4)
    agg = Aggregator(CLASSES, z=2.0, epsilon_budget=rdp_epsilon(2.0, 2) + 1e-9)
    ts = _tenants(4)
    assert [agg.run_round(ts, seed=i).status for i in range(3)] == ["OK", "OK", "REFUSED_PRIVACY_BUDGET"]
    assert len(agg.transcript) == 2 and all("aggregate" in r and "epsilon_cumulative" in r for r in agg.transcript)


def test_small_tenants_learn_faster_and_heterogeneity_is_reported() -> None:
    def avg(**kw):
        rs = [evaluate(seed=s, **kw) for s in range(5)]
        return {k: float(np.mean([r[k] for r in rs])) for k in rs[0] if k.startswith("mae")} | {"eps": rs[0]["epsilon"]}

    similar = avg(z=2.0, tau=0.3)
    assert similar["eps"] < 6.0
    assert similar["mae_collective_small"] <= 0.5 * similar["mae_local_small"]
    assert similar["mae_collective_large"] <= similar["mae_local_large"]
    strict = avg(z=8.0, tau=0.3)
    assert strict["eps"] < 1.5 and strict["mae_collective_small"] < strict["mae_local_small"]
    diverse = avg(z=2.0, tau=1.0)
    assert diverse["mae_collective_small"] < diverse["mae_local_small"]
    assert diverse["mae_collective_large"] > diverse["mae_local_large"]  # large, different tenants lose a little
