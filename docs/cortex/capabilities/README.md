# XiiD Cortex - the 15 capabilities: build status

Source of the capability list: *XiiD Cortex: Advanced Agentic AI Cybersecurity* blueprint (16 Nov 2026).
"Range" means implemented and tested against synthetic data and the in-repo reference
control plane. Nothing here is validated on a live XiiD deployment.

| # | Capability | Wave | Status | Doc |
|---|---|---|---|---|
| 01 | CyberTwin (+ calibration) | 1 | **Range**: twin, Beta beliefs, decay, risk intervals | [01](01-cybertwin-calibration.md) |
| 02 | GhostShift | 3 | **Range**: secret importance, CP-SAT rotation allocation, window schedule, drill. Uses PROPOSED tools | [02](02-ghostshift.md) |
| 03 | AutoHeal | 2 | **Range**: drift/down/silent-fault detection, hitting-set localisation, verified restore, model-checked FSM | [03](03-autoheal.md) |
| 04 | AgentShield | 2 | **Range**: purpose-based least privilege, blast radius, rug-pull check, behaviour monitor | [04](04-agentshield.md) |
| 05 | ProofGuard | 1 | **Range**: dual-ledger reconciliation, signed bundles, offline verifier | [05](05-proofguard.md) |
| 06 | BreachPath Eliminator | 1 | **Range**: exact CP-SAT optimiser, proven optimal, benchmarked | [06](06-breachpath.md) |
| 07 | Intent2Fabric | 1 | **Range**: controlled English → proved, monotone changes | [07](07-intent2fabric.md) |
| 08 | Predictive Exposure Radar | 2 | **Range**: mission-impact ranking, EPSS forecast, patch ordering, intel alerts | [08](08-exposure-radar.md) |
| 09 | CyberWarGame | 2 | **Range**: campaign simulation, paired playbook comparison, availability-aware recommendation | [09](09-cyberwargame.md) |
| 10 | DeceptionMesh | 3 | **Range**: placement to fire before loss, isolated deploy, bounded telemetry. Uses PROPOSED tools | [10](10-deceptionmesh.md) |
| 11 | Autonomous SOC Council | 3 | **Range, deterministic analysts**: routing, ACE challenge, evidence-bound output; model slot gated by admission (no model admitted) | [11](11-soc-council.md) |
| 12 | MissionGuardian | 1 | **Range**: windows, freezes, protected routes, scheduling | [12](12-missionguardian.md) |
| 13 | QuantumWatch | 3 | **Code + range**: crypto discovery, NIST IR 8547 / CNSA 2.0 profiles, Mosca risk, CP-SAT migration plan, CBOM | [13](13-quantumwatch.md) |
| 14 | Sovereign CyberSwarm | 4 | **Simulated regions**: release guard, signed HMAC'd summaries, store-and-forward, partner benefit | [14](14-cyberswarm.md) |
| 15 | Collective Immunity | 4 | **Research prototype**: secure aggregation + distributed DP, accounted ε | [15](15-collective-immunity.md) |

All 15 now have an implementation and tests. Two (GhostShift, DeceptionMesh) depend on
PROPOSED control-plane tools (contract 0.1.2) that XiiD has not built; the SOC Council runs
without any language model; CyberSwarm and Collective Immunity are simulations.

Wave 2 reuses the same path: AutoHeal and AgentShield execute through the same approvals,
broker and postcondition checks; the Radar and CyberWarGame run on the CyberTwin and feed
BreachPath.

All Wave 1 capabilities plug into one path: `DefenseCycle` →
MissionGuardian constraints → BreachPath / Intent2Fabric plan → device approvals → contract
v0.1 broker → per-step verification → rollback → ProofGuard bundle.
