# Capability 10 - DeceptionMesh

**Status:** implemented and tested in the range. The decoy tools are **PROPOSED** contract
extensions (contract 0.1.2: `decoy.deploy`, `decoy.retire`, `decoy.interactions`),
implemented only in the range control plane: **REQUIRES XIID VALIDATION**. Code:
`src/cortex/deceptionmesh/mesh.py`.

## What it does

A decoy has no legitimate users, so any touch is a high-fidelity signal. Its value depends
on placement, and placement is judged by one question: *does a decoy fire before a
protected asset falls?*

| Step | Method |
|---|---|
| Spread model | Same hourly model as CyberWarGame. Each run records when every node falls and when the first protected asset falls. |
| Touch model | A decoy attached at `u` is touched at the first hour after `u` falls in which the lure succeeds (15%/h placeholder). Draws are fixed per run and node, so every placement faces the same adversary luck. |
| Placement | Maximise P(touch before first loss): monotone submodular, so greedy has the (1 − 1/e) guarantee. It is also solved exhaustively for k ≤ 3 to measure the real gap. Greedy stops when no candidate adds detection: no decoys for show. |
| Rules | Internal only (internet attach refused by the control plane). Never attached to protected assets. Decoys run on their own hosts. One inbound lure route each, **no outbound route**. |
| Deploy / retire | Through approvals, broker and receipts. Verified afterwards: productive routes byte-identical, every new route is an inbound lure to a decoy, nothing leaves a decoy. Retiring restores the original inventory exactly. |
| Telemetry | `decoy.interactions` returns who, first/last seen, count and depth (0 connect … 4 data request). **Never payloads**; the schema has no field for them. |
| Response | Interactions become evidence (implicated hosts) for GhostShift rotation and for containment. |

## Measured (tests/cortex/test_deceptionmesh.py, 6 tests)

**In-sample** (the 3 war-game campaigns, 150 runs each). P(decoy touched before first loss):

| Decoys | Greedy | Exhaustive optimum | Next to crown jewels | Random |
|---|---|---|---|---|
| 1 | 0.46 | 0.46 | 0.42 | 0.14 |
| 2 | 0.75 | 0.75 | 0.42 | 0.27 |
| 3 | **0.90** (alarm ≈ 30 h before the first loss) | 0.90 | 0.58 | 0.39 |

**With CyberWarGame, phishing campaign, quarantine playbook:** 3 decoys cut protected assets
lost from 3.75 to 1.49. The paired interval excludes zero.

**Unseen campaigns, stated plainly.** The in-sample figures are optimistic. Trained on every
*other* entry point and tested on the held-out campaign, the robust placement is:
- better than random on all three;
- better than crown-jewel placement on two (0.56 vs 0.39 for phishing, 0.40 vs 0.00 for the insider);
- worse on internet entry (0.51 vs 0.76).

The test asserts exactly this. Placement should be trained on the customer's threat model
(likely entry points), not on a generic one.

## Limits

- Lure probability and attacker interest in decoys are placeholders. Real adversaries may
  recognise and avoid decoys.
- Decoy services are not emulated in the range. Only the control-plane behaviour (placement,
  isolation, telemetry) is tested.
- The decoy tools, isolation guarantees and interaction telemetry must be built and
  confirmed by XiiD.
