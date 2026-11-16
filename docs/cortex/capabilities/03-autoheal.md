# Capability 03 - AutoHeal

**Status:** implemented and tested in the synthetic range with injected faults. The flow
generator does not yet make an STLink outage stop traffic, so `stlink_down` is detected
from inventory, not from symptoms.

## What it does

AutoHeal restores the **approved** state of the fabric, never something new, and never ends
up more exposed than the approved baseline. Code: `src/cortex/autoheal/`.

| Step | Method |
|---|---|
| Detect | Drift: route state ≠ approved baseline. Down: STLink not `active`. Symptoms: each required flow is a probe. Zero sessions in the last hour where the baseline predicts ≥ 5 (Poisson P(0) ≤ 0.7%) is *failed*; any traffic is *healthy*; otherwise *inconclusive*. |
| Localise | Failed probes not explained by a direct fault are covered by a minimum set of components (exact hitting set, CP-SAT). Any component carrying a healthy probe is exonerated; ties prefer a shared STLink over several tunnels. A symptom with no candidate is escalated. |
| Plan | One restoration per fault (`restore_route`, `narrow_route` to the baseline prefix, `expire_route` for unauthorised re-activation, `enable_stlink`, `deploy_stlink` for silent failures). The simulated exposure must not exceed the approved baseline. Protected routes (MissionGuardian `R-NO-AUTO-*`, `R-CCTV-*`) escalate. Repairs are ordered by mission tier. |
| Authorise | The same device approvals and approval tokens as the defense cycle; restoration is not a free pass. Class D repairs need two approvers. |
| Repair → verify | Each repair is checked against fresh inventory, then every probe is re-run. A signed receipt is never treated as proof. |
| Escalate | Repairs restore approved state, so there is no meaningful inverse; failure escalates to an operator. |

**Incident state machine** (`fsm.py`): one transition table drives both runtime and model
check. Exhaustive exploration of every event sequence (11 states, 8 complete paths) proves:
- no `REPAIRING` without `AUTHORIZED`;
- no `RESOLVED` without `VERIFYING`;
- terminal states absorb all events;
- every reachable state can terminate, with no cycles.

A mutation test confirms the checker catches a table that skips authorisation.

## Measured (tests/cortex/test_autoheal.py, 11 tests)

| Injected fault | Outcome |
|---|---|
| None | `CLOSED_NO_FAULT`, 0 writes, at least 10 healthy probes |
| ERP user route expired out of band | `RESOLVED` via `restore_route` |
| Approved-expired route re-activated | `RESOLVED` via `expire_route`; exposure within baseline |
| HR-DB STLink disabled | `RESOLVED` via `enable_stlink` with 2 approvals |
| **Silent:** NVR STLink "active" but its tunnels carry nothing | Both CCTV probes failed; localised to `stlink:stlink-srv-nvr-01` (not the 2 tunnels); `deploy_stlink`; probes healthy after; `RESOLVED` |
| Kerberos route to the DC expired | `ESCALATED` (`R-NO-AUTO-IDENTITY`), 0 writes |
| Redeploy acknowledged but not applied | Postcondition passed (status active), fresh probes still failed → `ESCALATED` |
| Approvers deny | `ESCALATED`, 0 writes |

## Limits

- Probes use flow aggregates; production should add synthetic transactions per critical flow.
- No reroute strategy: the contract has no alternative-path primitive.
- One incident at a time; concurrent incidents on shared components are not coordinated.
- The finite state machine is checked by exhaustive enumeration in Python, which is complete
  for this table. A TLA+ export for the CI `tla` job is a follow-up.
