# Capability 05 - ProofGuard

**Status:** implemented and tested in the synthetic range. Cryptographic integrity proves
who recorded and signed what; it does **not** prove a decision was correct.

## Dual-ledger reconciliation (`src/cortex/proofguard/ledger.py`)

Cortex records every write it sent and the control plane's signed receipt (contract-client
`write_log`). The control plane records every change it applied (`change.applied` events),
read here by a separate auditor identity in `sbx-observe`. Reconciling the two exposes:

| Discrepancy | Severity | Meaning |
|---|---|---|
| `UNACCOUNTED_CHANGE` | critical if made under Cortex's client id, else high | A change Cortex never sent: rogue agent, out-of-band admin, or stolen Cortex credentials |
| `MISSING_IN_CONTROL_PLANE` | high | Cortex holds a receipt the control plane's ledger omits |
| `RECEIPT_DIGEST_MISMATCH` | critical | The receipt does not hash to what Cortex sent and received |
| `RECEIPT_SIGNATURE_INVALID` | critical | The receipt is not signed by the pinned control-plane key |
| `APPROVAL_MISMATCH` | critical | The receipt cites a different approval than Cortex attached |
| `ACKNOWLEDGED_NOT_APPLIED` | high | Valid signed receipt, but Cortex's independent observation shows no effect; the control plane is on record for a change it did not make |

Receipts are verified offline. Cortex rebuilds the exact record the control plane signed
from what it sent and received, so no server call is needed.

## Case bundle and offline verifier (`src/cortex/proofguard/bundle.py`)

One signed JSON file (about 73 KB for a 4-change cycle) holds:

- the cycle report;
- the complete Cortex Merkle audit log, verbatim, and its head (count, last hash, Merkle root);
- the write ledger with receipts;
- the control-plane change ledger;
- the reconciliation;
- an Ed25519 signature by the evidence key.

```bash
python -m src.cortex.proofguard.bundle verify case.json --evidence-key <b64> --receipt-key <b64>
# exit 0 valid, 2 problems found
```

The reviewer supplies both public keys; keys inside the bundle are never trusted. Checks:
bundle signature; audit chain (the log's own verifier); head (catches truncation);
reconciliation recomputes identically; every change reported as executed has a receipt;
completed writes in the audit log equal the write ledger.

## Measured (tests/cortex/test_proofguard.py, 9 tests)

| Scenario | Detected as |
|---|---|
| Clean 4-write cycle | valid; 4/4 writes matched |
| One audit entry edited | `BUNDLE_SIGNATURE_INVALID`, `AUDIT_CHAIN_BROKEN`; the chain still breaks if the attacker re-signs with the evidence key |
| Last 3 audit entries removed | `BUNDLE_SIGNATURE_INVALID`, `AUDIT_HEAD_MISMATCH` |
| A write deleted and the bundle re-signed | `RECONCILIATION_DOES_NOT_RECOMPUTE`, `WRITE_LEDGER_MISMATCH` |
| A write's result altered | `RECEIPT_DIGEST_MISMATCH`, `RECEIPT_SIGNATURE_INVALID` |
| Another admin expires a route out of band | `UNACCOUNTED_CHANGE` (high), naming the principal |
| Same, using Cortex's own client key | `UNACCOUNTED_CHANGE` (**critical**) |
| SIM-005: write acknowledged but not applied | `ACKNOWLEDGED_NOT_APPLIED`; evidence itself valid |

## Limits

- Someone holding the evidence key *and* able to rewrite the whole audit chain could forge a
  consistent bundle. Mitigation: anchor periodic checkpoints outside Cortex (the
  control-plane audit head, or an external timestamp service). Not yet implemented.
- Reading the control-plane change ledger currently uses `telemetry.events`; a dedicated
  auditor scope and a paged `audit.changes` tool should be added to contract v0.2.
