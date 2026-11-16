# Capability 12 - MissionGuardian

**Status:** implemented and tested in the synthetic range. Policy content is illustrative;
a real deployment needs the mission owner's own tiers, windows and rules.

## What it does

It turns mission rules into hard constraints that no planner can trade away for risk reduction.

| Function | Purpose |
|---|---|
| `compile_constraints(now)` | Limits every planner must obey *now*: protected routes, closed change windows, tier disruption caps, plan-size limit, active freezes. Feeds BreachPath `PlanConstraints`. |
| `validate(plan, now)` | Independent check of any finished plan from any planner. Returns every violated rule by id. Options with violations cannot be recommended. |
| `schedule(plan, now)` | Earliest compliant window per change, honouring tier windows and per-segment concurrency (CP-SAT). |

A route takes the **lowest (most critical) tier** of any mission whose flow depends on it
or whose asset it reaches. Policy: `range/enterprise/mission_policy_enterprise_200.yaml`
(5 missions, 3 tiered windows, 6 rules). Code: `src/cortex/missionguardian/guardian.py`.

## In the defense cycle

`DefenseCycle(mission_guard=..., clock=...)`:

1. Compiles constraints at planning time and passes them to the exact optimiser (OPT-D).
2. Validates every option; any option with a violation is not recommendable.
3. If nothing is allowed now, the outcome is **`scheduled`**, with the deferred plan and its window assignment.
4. Re-validates each change just before its write; if the window has closed, it stops, rolls back and escalates.

The clock is injectable, so a Friday-night window can be rehearsed on a Monday morning.

## Measured behaviour (enterprise_200, target exposure 0.30)

| Planning time (Riyadh) | Executed plan | Reason |
|---|---|---|
| Mon 16 Nov 10:00 | none - **scheduled**: ERP route Mon 22:00, jump host Fri 22:00 | Both changes touch tier 1 or 2 missions outside their windows |
| Mon 16 Nov 23:00 | expire `rt-users-erpdb` | Tier 2 window open; tier 1 jump-host change waits |
| Fri 20 Nov 23:00 | narrow `rt-users-jump-rdp` | National-event freeze forbids irreversible changes (current XiiD contract) |
| Fri 27 Nov 23:00 | both changes | All windows open |

A deliberately bad plan (expire the CCTV ingest route, narrow the Kerberos route) was rejected
with `R-CCTV-SAFETY`, `R-REQUIRED-FLOW`, `R-TIER-DISRUPTION`, `R-NO-AUTO-IDENTITY` and `W-TIER-1`.

## Limits

- Rule evaluation is deterministic code, not formal verification. A TLA+ model of the
  window/freeze/rollback interaction is planned with AutoHeal.
- OT safety is expressed as protected routes and windows. Process-state-aware rules
  (for example, "only when the line is stopped") need live OT state, which the twin does not have yet.
- The scheduler plans one cycle; it does not coordinate across concurrent cycles.
