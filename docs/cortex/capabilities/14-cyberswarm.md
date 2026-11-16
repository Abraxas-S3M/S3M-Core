# Capability 14 - Sovereign CyberSwarm

**Status:** implemented and tested with simulated regions in one process. There is no real
cross-domain transport or hardware guard; those are deployment work. The cross-region
benefit is measured on war-game campaigns. Code: `src/cortex/swarm/swarm.py`, policy in
`configs/cortex/swarm_policy.yaml`.

## What it does

Each region is an isolated Cortex deployment. Only **threat summaries** cross a boundary:

`summary_id, origin, recipients, issued_at, ttl_hours, kind, technique, indicator_hmac, severity, confidence, observations_bucket, classification, recommended_capability`

- **Indicators** cross only as an HMAC under a community key. A partner can test "have I
  seen this?" against its own observations. A party without the key learns nothing.
- **Release guard (outbound):**
  - field whitelist;
  - scan for addresses, inventory names and raw indicators;
  - k-anonymity (≥ 3 local observations), with counts bucketed;
  - recipient must be a partner cleared for the classification, and the origin must itself
    be cleared for it;
  - a release officer for `secret`;
  - per-recipient rate limit.
- **Admission (inbound):** Ed25519 signature by the registered origin key, intended
  recipient, partner relationship, schema, TTL, replay cache.
- **Links:** store-and-forward. A partition queues summaries and delivery resumes in order.
- **Local use:** matched indicators raise local cases (SOC Council) and drive a hunt.
  Summaries recommend a capability; nothing executes remotely.

## Measured (tests/cortex/test_cyberswarm.py, 13 tests)

**Sovereignty:**
- The released wire format contains no raw indicator, host name or address.
- Every leak path is blocked: an address in a field, an inventory name, a raw indicator,
  k = 2, an unknown partner, an uncleared recipient or origin, a missing release officer, an
  extra field such as a raw log line, and the rate limit.
- Tampering, replay, expiry, misdelivery and unknown origins are all rejected on admission.

**Partner benefit:** the same adversary reaches a partner region after a lag. With the
swarm, the origin's first detection becomes a summary 2 h later, and the partner hunts for
the indicator (detection ×5) from then on. Quarantine playbook, 120 paired runs:

| Campaign, lag | Partner assets lost without → with | Significant? |
|---|---|---|
| Insider on CI server, 72 h | 1.67 → **0.80** | yes |
| Insider, 24 h | 1.67 → 1.08 | yes |
| Phishing, 72 h | 3.67 → 3.35 | yes (small) |
| Internet entry, 24 h | 3.48 → 3.41 | **no**; the test asserts the interval includes 0 |

The swarm helps against slower, quieter campaigns. Against fast internet-borne spread, the
partner is already lost before the hunt starts.

## Limits

- The hunt factor (×5) and the lag are assumptions. Real value depends on how well partner
  SOCs can act on an indicator.
- Community-key management (distribution, rotation, revocation) and region signing keys
  need a sovereign PKI. Ed25519 is quantum-vulnerable; see QuantumWatch for its migration.
- One process simulates the regions. A deployment needs a real cross-domain solution
  between classification levels.
