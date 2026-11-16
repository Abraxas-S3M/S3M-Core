# XiiD Cortex - the 15 capabilities: build status

Source of the capability list: *XiiD Cortex: Advanced Agentic AI Cybersecurity* blueprint (16 Nov 2026).
"Range" means implemented and tested against synthetic data and the in-repo reference
control plane. Nothing here is validated on a live XiiD deployment.

| # | Capability | Wave | Status | Doc |
|---|---|---|---|---|
| 01 | CyberTwin (+ calibration) | 1 | **Range**: twin, Beta beliefs, decay, risk intervals | [01](01-cybertwin-calibration.md) |
| 02 | GhostShift | 3 | Not started; needs new XiiD rotation tools | - |
| 03 | AutoHeal | 2 | **Range**: drift/down/silent-fault detection, hitting-set localisation, verified restore, model-checked FSM | [03](03-autoheal.md) |
| 04 | AgentShield | 2 | **Range**: purpose-based least privilege, blast radius, rug-pull check, behaviour monitor | [04](04-agentshield.md) |
| 05 | ProofGuard | 1 | **Range**: dual-ledger reconciliation, signed bundles, offline verifier | [05](05-proofguard.md) |
| 06 | BreachPath Eliminator | 1 | **Range**: exact CP-SAT optimiser, proven optimal, benchmarked | [06](06-breachpath.md) |
| 07 | Intent2Fabric | 1 | **Range**: controlled English → proved, monotone changes | [07](07-intent2fabric.md) |
| 08 | Predictive Exposure Radar | 2 | **Range**: mission-impact ranking, EPSS forecast, patch ordering, intel alerts | [08](08-exposure-radar.md) |
| 09 | CyberWarGame | 2 | **Range**: campaign simulation, paired playbook comparison, availability-aware recommendation | [09](09-cyberwargame.md) |
| 10 | DeceptionMesh | 3 | Not started; needs new XiiD decoy tool | - |
| 11 | Autonomous SOC Council | 3 | Blocked: no admitted model | - |
| 12 | MissionGuardian | 1 | **Range**: windows, freezes, protected routes, scheduling | [12](12-missionguardian.md) |
| 13 | QuantumWatch | 3 | Not started (crypto inventory file exists) | - |
| 14 | Sovereign CyberSwarm | 4 | Not started | - |
| 15 | Collective Immunity | 4 | Research; not started | - |

Wave 2 reuses the same path: AutoHeal and AgentShield execute through the same approvals,
broker and postcondition checks; the Radar and CyberWarGame run on the CyberTwin and feed
BreachPath.

All Wave 1 capabilities plug into one path: `DefenseCycle` →
MissionGuardian constraints → BreachPath / Intent2Fabric plan → device approvals → contract
v0.1 broker → per-step verification → rollback → ProofGuard bundle.
