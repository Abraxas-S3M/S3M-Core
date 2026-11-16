# Capability 07 - Intent2Fabric

**Status:** implemented and tested in the synthetic range. No language model is used; a
model may later *suggest* sentences in the controlled language, never act on them.

## Pipeline

1. **Controlled English → typed intent** (`parse`). There are four sentence forms; anything
   else is rejected with the accepted forms listed. Names and services must exist in the
   twin; prefixes must be canonical. Each intent renders a canonical sentence that parses
   back to the same intent, which is what the operator confirms.

   | Form | Example |
   |---|---|
   | only reach | `grp:cctv-cams may only reach srv-nvr-01` |
   | only reachable from | `only srv-erp-app-01, srv-backup-01 and srv-jump-01 may reach srv-erp-db-01` |
   | deny services | `no ssh, rdp, smb from ext:internet` |
   | restrict prefix | `grp:corp-users may reach srv-file-01 over smb only from 10.10.4.0/22` |

2. **Compile** (`compile_intents`): every violating route becomes one change, either expire
   or narrow for prefix intents. A route that carries a required mission flow is never
   expired; it is reported as a **conflict** with the flow id, for the operator to resolve.

3. **Prove** (`verify`): re-evaluates every intent over *all* simulated post-change routes.
   That is exhaustive over a finite set, so the check is exact for these forms. It also checks:
   - **monotone tightening**: no route added and no prefix widened (subnet containment);
   - required flows intact.

4. **Execute**: `DefenseCycle(intents=...)` wraps the plan as **OPT-I** and sends it through
   MissionGuardian, device approvals, the broker, per-step verification and rollback.

Code: `src/cortex/intent2fabric/intents.py`. Example intents: `range/enterprise/intents_enterprise_200.yaml`.

## Measured (enterprise_200)

- 5 intents → 5 changes: expire `rt-cams-corp`, `rt-users-erpdb`, `rt-inet-jump-ssh`,
  `rt-mail-file`; narrow `rt-users-file` to 10.10.4.0/22.
- Proof: all satisfied, monotone, flows intact; 42 → 38 active routes.
- Executed through contract v0.1: 5 writes, verified.
- An over-broad intent ("corp users may only reach ERP and HR") produced conflicts on
  `rt-users-dc` (F-AUTH), `rt-users-file` (F-FILE) and `rt-users-siem` (F-LOGS) instead of breaking them.
- 60 random intents: none widened access or broke a flow.

## Limits

- Intents describe *direct* permitted routes. Transitive isolation ("cannot reach X by any
  path") is BreachPath's job; combining the two is a planned extension.
- Narrowing assumes the target prefix covers every legitimate consumer. Flow telemetry
  (TELEMETRY.md) should confirm that before approval.
