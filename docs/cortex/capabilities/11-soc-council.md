# Capability 11 - Autonomous SOC Council

**Status:** implemented and tested with **deterministic analysts only**. No language model
is admitted for this deployment. Quarantined weights were not loaded and no GPU was used.
The council includes a policy-gated slot for an approved model analyst. Measurements use a
synthetic case corpus with ground truth. Code: `src/cortex/soccouncil/`.

## What it does

| Blueprint element | Implementation |
|---|---|
| Route specialists by trusted case type | `ROUTING`: `alert_triage` → deception + AgentShield analysts; `attack_path` → deception + exposure; `change_review` → fabric. The case type comes from SOC code. Alert text is never read, and an unknown type is refused. |
| Specialist analysts | Each emits structured claims citing case evidence ids. **Deception:** decoy touch → host compromised. **AgentShield:** behaviour alarm (+ denied calls) → agent misuse. **Fabric:** drift → unauthorised change. **Exposure:** best twin attack path from a suspected host to each protected asset, citing every route and finding on the path. |
| Challenge high-impact findings | Every high or critical claim goes through the existing ACE `cross_examine`: grounding filter (uncited, or cited outside the case → dropped), a **distinct-family** challenger (enforced), refutation, and a reliability record. The challenger names its counter-evidence: authorised scanner, connect-only single touch, stale evidence (> 24 h), a path route expired since the snapshot, an approved change receipt, an alarm in a maintenance window with no denied call. |
| Evidence-bound recommendations | Only accepted claims, each with its evidence ids. Each yields a *proposed* follow-up for a Cortex capability (GhostShift, BreachPath, AgentShield, AutoHeal) that requires operator approval through the normal change path. The council executes nothing. |
| Model slot | `model_slot_from_policy(engine)` admits an LLM analyst only if the model-admission policy marks the engine routable (quarantined → refused). Analysts already speak the ACE line protocol, so an admitted model plugs into the same path. Every result states the model status. |

## Measured (tests/cortex/test_soc_council.py, 6 tests)

The corpus has 60 cases × 3 case types, generated from adversary spread on the twin. Noise
includes a scanner, connect-only probes, stale evidence, routes expired after the snapshot,
maintenance-window alarms and approved changes. It also includes an *unrefutable* curious
administrator.

| High-impact claims | Without challenge | With challenge |
|---|---|---|
| Precision | 0.84 | **0.99** |
| Recall of proposed true claims | 1.00 | 0.94 |
| False claims accepted | 87 | 6 |

| Case type | Precision without → with challenge |
|---|---|
| change review | 0.50 → 1.00 (approved changes recognised by receipt) |
| attack path | 0.92 → 0.98 (paths through since-expired routes refuted) |
| alert triage | 0.99 → 0.99 |

The recall cost comes mostly from true but stale evidence, which the challenger rejects by
design.

Also tested:
- An injected alert body changes nothing.
- An unknown case type is refused.
- A same-family challenger is refused.
- A quarantined engine is never admitted.

## Limits

- The analysts are rules over structured evidence. They do not read free text, so they
  cannot do the open-ended reasoning an admitted model could. That is the model slot's job,
  once admitted and validated on real cases.
- The corpus is synthetic. Precision and recall on real SOC cases must be measured before
  any claim.
- Low-impact claims are reported but not challenged.
