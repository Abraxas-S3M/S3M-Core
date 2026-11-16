# Capability 04 - AgentShield

**Status:** implemented and tested in the synthetic range. The blueprint's acceptance proof
passes in the range: an agent with deliberately excessive tool and network permissions is
identified; unauthorised paths are rejected at the control plane while approved tasks
continue. The behaviour monitor is measured on synthetic traces only. Code:
`src/cortex/agentshield/`.

## Components

| Blueprint component | Implementation |
|---|---|
| Agent registry | `range/enterprise/agents_enterprise_200.yaml`: agent, owner, purpose, host, sandbox; MCP servers; agent-host routes |
| Purpose-to-permission mapping | `configs/cortex/agent_purposes.yaml`: per purpose, the exact contract tools, resource selectors, network targets, write rate and redaction. `review.py` compares grant with purpose: tools (via sandbox, scopes and classes), resources (via selectors), routes from the agent host, and the **blast radius** of a hijacked agent host (max attack-path probability to each protected asset, CyberTwin). |
| Least privilege | `least_privilege_profile()` emits a sandbox profile granting exactly the purpose, with read scoping on. It is never widened by observed behaviour; calls the purpose does not justify are reported as `used_outside_purpose` for a human. Excess routes become `expire_route` changes, each with approvals, broker, postcondition and inverse. |
| MCP manifest checks | `manifest_check.py`: live `tools/list` vs pinned contract (drift) plus instruction-like text in tool metadata (override phrases, imperatives to the agent, mass actions, URLs, hidden Unicode, encoded blobs, markup). Any non-`pinned` verdict blocks the server. No false positives on the 25 contract descriptions. |
| Policy anomaly signals | `behavior.py`: purpose-conditioned Markov model of tool sequences with a Chinese-restaurant resource-novelty term; per-call surprisal accumulated by one-sided CUSUM; `k` and `h` fitted on held-out normal sessions for a 1% per-session false-alarm target. |
| Agent-aware access review | `AccessReview` per agent: verdict, excess by class, excess resources, excess routes, blast radius before and after, score, recommended profile. |

## Measured

**Acceptance proof** (`tests/cortex/test_agentshield.py`, `agent-helpdesk`, purpose
`ticket_triage`, deliberately granted `sbx-range-full` plus routes to the ERP DB and jump host):

| | Before | After AgentShield |
|---|---|---|
| Verdict | excessive (21 excess tools incl. 5 class D, 2 excess routes), ranked first of 3 agents | - |
| Blast radius to ERP DB / DC | 0.496 / 0.210 | 0 / 0 |
| Its approved tasks (health, routes, flow of `rt-users-erp`) | succeed | succeed |
| `route.expire`, `stlink.disable` with a forged approval | would reach approval checks | `FORBIDDEN_SCOPE` |
| `inventory.list_hosts` | allowed | `SANDBOX_DENIED` |
| Flows of `rt-users-dc` / all flows | allowed | `RESOURCE_DENIED` |
| Its SIEM route / ERP-DB and jump routes | active | active / expired (approved changes) |

All 5 rejections happen at the control plane (the test bypasses client pre-checks, as a
hijacked agent would) and are logged with the agent's client id. The other two agents are
also flagged: their grants include reads their purposes do not need.

**Rug pull:** a server-side change to `route.narrow`'s description is reported `suspicious`
(markers `override_instruction`, `mass_action`) and blocks the server.

**Behaviour monitor, synthetic `ticket_triage` traces, 3 seeds:**

| Session type | CUSUM monitor | Tool allowlist (static review) |
|---|---|---|
| Normal (false alarm) | ≤ 2% (0% at seed 7) | 0% |
| Recon burst (list hosts, sessions, tunnels, audit) | ≥ 95%, first call | 100% |
| Out-of-purpose write | ≥ 95% | 100% |
| Harvest: allowed tool over 12 unseen routes | ≥ 95%, ~1.1 calls | **0%** |
| Low-and-slow: one unseen route in a normal session | > 80% (91.5% at seed 7) | **0%** |

The monitor's value is the bottom two rows: misuse of *permitted* tools. A low-and-slow call
that lands on a route the agent already uses is indistinguishable from normal and is missed.
On the broader `exposure_reporting` purpose (15-route working set) low-and-slow detection
falls to 69%.

## Limits

- Traces are synthetic. Real agent traffic needs re-fitting and a measured false-alarm rate
  before the monitor raises anything above "review".
- The range control plane logs every call; production depends on the XiiD MCP agent's audit
  log exposing the same fields (**REQUIRES XIID VALIDATION**).
- Agent-to-agent connectivity is modelled only as routes between agent hosts; there is no
  agent identity in the data plane yet.
- List tools are not filtered by resource selectors.
- Provisioning a profile is direct in the range; in production it is an access-review ticket
  to the XiiD and identity-provider administrators.
