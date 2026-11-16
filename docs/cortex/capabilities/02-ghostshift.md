# Capability 02 - GhostShift

**Status:** implemented and tested in the range. The blueprint's acceptance proof passes in
the range: rotations run with service continuity, signed audit evidence and no change in
reachability. **The two rotation tools do not exist in XiiD today.** They are PROPOSED
contract extensions (contract 0.1.1, `status: proposed`), implemented only in the range
control plane: **REQUIRES XIID VALIDATION**. Code: `src/cortex/ghostshift/`.

## What moves

GhostShift does not shuffle routes. Reachability stays exactly as approved. What moves is
the *secrets an adversary may already hold*:

| Proposed tool | Effect | Class / approvals |
|---|---|---|
| `stlink.rotate_identity(stlink_id, grace_seconds)` | New STLink credential; the old one works only until the grace period ends | C, not reversible → 2 approvals |
| `tunnel.rekey(tunnel_id)` | New SealedTunnel keys; route and endpoints unchanged | C, not reversible → 2 approvals |

## Method

| Step | Method |
|---|---|
| Importance | Path-specific: for each sealed route a secret protects, `reach(source) × (p_unsealed − p_sealed) × Σ_a P(target → a)` on the CyberTwin. The network-wide max-path metric is deliberately not used: it hides defence-in-depth value whenever a weaker parallel path exists. |
| Acquisition | Poisson, at a base rate per kind (STLink 1/180 days, tunnel 1/365 days) × how reachable the host is from the footholds. |
| Value of rotating | Expected time an adversary holds a valid secret with `n` evenly spaced rotations: `(n+1)·g(H/(n+1))`, `g(L) = L − (1 − e^(−aL))/a`. Checked against Monte Carlo within 3%. |
| Allocation | CP-SAT multiple-choice knapsack: rotations per secret under a stability budget and a minimum interval, minimising importance × held time + disruption. **Zero-importance secrets are never rotated.** |
| Schedule | Even spacing snapped to MissionGuardian windows for the tier the secret serves (tier 1: Friday 22:00), with a per-window cap. |
| Event trigger | Compromise evidence (host, route or secret) selects the implicated secrets for the next window. |
| Execution | Same approvals, broker and signed receipts as every change. Postcondition: the epoch advanced. Then: routes unchanged, twin exposure unchanged, every mission flow healthy (AutoHeal probes). The first failure stops the drill. Secrets on identity, PKI and CCTV infrastructure are planned but **operator-only**. |

## Measured (tests/cortex/test_ghostshift.py, 8 tests)

**Drill on the range control plane:**
- The synthetic adversary harvests the ERP-DB STLink credential, the DC STLink credential and the ERP-DB tunnel key; all three replay successfully.
- GhostShift rotates the ERP-DB credential and key, each with 2 approvals and a signed receipt. Afterwards the harvested ERP-DB credential and key are rejected.
- The DC credential is untouched (operator-only) and still works, as it should: the tests show what was *not* done.
- Routes and exposure are identical before and after, and AutoHeal closes with no fault.

**Allocation (90 days, enterprise_200)**, adversary-held secret time × importance:

| Rotation budget | GhostShift | Same period for every secret | Reduction |
|---|---|---|---|
| 6 | 5.34 | 8.92 | 40% |
| 12 | 3.88 | 8.09 | 52% |
| 24 | 2.57 | 4.72 | 46% |

Three secrets (jump-host STLink, admins → jump tunnel, cameras → NVR tunnel) protect paths
no foothold reaches, so they are never rotated, whatever the budget.

## Limits

- Rotation tools are proposals; grace semantics, re-enrolment of STLink agents and rekeying
  without dropping sessions must be confirmed by XiiD.
- Acquisition rates are placeholders; the importance model inherits the twin's heuristic
  edge probabilities.
- Route-level moving target (re-binding routes to alternative connectors) is not modelled:
  the range has no alternative paths.
