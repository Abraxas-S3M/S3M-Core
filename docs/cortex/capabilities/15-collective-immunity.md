# Capability 15 - Collective Immunity

**Status:** research prototype, implemented and tested on a synthetic federation of 10
tenants. The blueprint puts it at "Research"; it stays there until real tenants, a legal
basis for exchange and an external privacy review exist. Code:
`src/cortex/immunity/federated.py`.

## What it learns

Per service class: how often a *reviewed* attack attempt succeeded. CyberTwin calibration
needs exactly this quantity, and a small tenant can barely estimate it alone. Each tenant
shrinks its own estimate toward the collective rate (Beta prior, strength 20). A tenant with
plenty of data therefore keeps its own signal.

## Protocol (per round)

| Safeguard | Implementation |
|---|---|
| Raw logs never leave | Each tenant reduces analyst-reviewed incidents to a count vector (attempts, successes per class). Unreviewed incidents and opted-out tenants are excluded. |
| Bounded influence | At most `cap` incidents per class per tenant per round. |
| Distributed differential privacy | Each tenant adds `N(0, σ²/n)` noise, so the sum carries `N(0, σ²)` without a trusted aggregator. Unit: one incident (L2 sensitivity √2), `σ = z·√2`. Rényi-DP accounting across rounds. A round that would exceed the privacy budget is refused. |
| Secure aggregation | Pairwise masks from X25519 key agreement + HKDF, added mod 2³² in fixed point. The aggregator sees uniform-looking vectors, and the masks cancel exactly in the sum. A missing participant aborts the round. |
| Plausibility | A sum outside `[−slack, n·cap + slack]` aborts the round (gross poisoning). |
| Governance | Opt-in per tenant; a transcript per round (participants, aggregate, cumulative ε) that tenants can audit. |

## Measured (tests/cortex/test_collective_immunity.py, 6 tests; 5 seeds, 4 rounds)

Mean absolute error of per-class success rates vs each tenant's truth:

| Federation | Privacy (ε, δ = 10⁻⁶) | Small tenants: local → collective | Large tenants: local → collective |
|---|---|---|---|
| Similar tenants (logit spread 0.3) | 5.8 | 0.137 → **0.049** | 0.041 → 0.033 |
| Similar tenants | 1.3 (strict) | 0.137 → 0.067 | 0.041 → 0.036 |
| Diverse tenants (logit spread 1.0) | 5.8 | 0.141 → 0.122 | 0.035 → **0.039 (worse)** |

Small tenants gain a lot, especially when tenants resemble each other. When they differ, a
large tenant is slightly hurt by being pulled toward the collective; the test asserts that
direction rather than hiding it. Per-tenant adaptive shrinkage is the obvious next step.

Also tested:
- Masks cancel exactly, a masked vector looks random, and masks differ per round.
- Dropout and gross poisoning abort the round.
- **Poisoning within the cap is not detectable** under secure aggregation. Its effect is
  bounded by one tenant's share of the attempts (measured, and asserted ≤ 0.145 here).

## Limits

- Dropout recovery (secret-shared masks) and verifiable clipping (range proofs) are not
  implemented. Without them, an honest-but-curious aggregator is assumed and within-cap
  poisoning is possible.
- The privacy unit is one incident. Tenant-level privacy (hiding whether a tenant
  participated at all) needs far more noise or many more tenants.
- Synthetic data only. Real use needs a data-sharing agreement, sovereignty review (see
  CyberSwarm) and an independent privacy assessment.
