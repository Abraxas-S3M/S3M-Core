# Capability 09 - CyberWarGame

**Status:** implemented and tested on the synthetic enterprise_200 twin. Attack timing and
detection rates are assumptions, not measurements. Treat the results as *relative*
comparisons between playbooks, not forecasts of a real incident. Code:
`src/cortex/wargame/wargame.py`.

## What it does

The war game runs many synthetic campaigns on the CyberTwin. It compares containment
playbooks on the same attacker and detection draws (common random numbers), so differences
come from the playbook and not from luck.

| Element | Model (defaults) |
|---|---|
| Campaign | Entry node(s); 168 hourly steps. An edge with twin probability `p` succeeds with hourly probability `p / 24`. Identity edges can be traversed but not cut. |
| Detection | Each compromised node, each hour: servers 2%, protected assets 5%, user groups 0.5%. |
| Response | The playbook runs once, 2 h after the first detection, using only *detected* nodes. Undetected footholds keep spreading. |
| Playbooks | `none`; `quarantine_detected` (isolate detected nodes); `cut_egress` (expire routes out of detected nodes); `ring_fence_assets` (expire routes into protected assets except tier-1 flows); `breachpath_adaptive` (BreachPath with detected nodes as extra footholds, tier-1 routes untouchable). |
| Metrics | Protected assets lost; tier-weighted flow-hours lost (tier 1 = 10, tier 2 = 3, tier 3 = 1); whether the attacker was contained. |
| Statistics | Paired bootstrap 95% intervals on per-run differences; Pareto front over (assets lost, flow-hours lost); a recommendation within an availability budget. |

## Measured (tests/cortex/test_wargame.py, 7 tests; 150 runs per campaign)

| Campaign | none | quarantine | cut egress | ring-fence | BreachPath adaptive |
|---|---|---|---|---|---|
| Insider on CI server: assets lost / flow-hours | 3.59 / 0 | 1.78 / 860 | 2.39 / 88 | **1.65** / 1124 | 2.10 / **0** |
| Internet entry via VPN | 3.94 / 0 | 3.48 / 1012 | 3.67 / 445 | 3.59 / 1068 | 3.51 / **0** |
| Phishing (corporate users) | 4.15 / 0 | 3.78 / 1565 | 3.88 / 691 | 3.92 / 1173 | 4.00 / **0** |

(200-run figures at seed 1; the tests assert the same relations at 150 runs.)

Findings the tests lock in:
- Every playbook beats doing nothing in the insider and VPN campaigns (interval excludes 0).
- The optimised cut never takes a required flow down and is on the Pareto front. With an
  availability budget of 200 flow-hours it is the recommendation.
- With no availability limit the war game recommends ring-fencing or quarantine for the
  insider case, and makes the price explicit (≈ 1,100 flow-hours).
- **No overclaiming:** in the VPN campaign the optimised cut and quarantine are
  statistically indistinguishable, and the test asserts that.
- **Phishing:** detection is the bottleneck. Raising user-segment detection from 0.5% to 5%
  per hour cuts losses under quarantine by more than 0.7 assets. Route cuts alone barely
  help, because the dominant path runs through the protected Kerberos route and identity
  edges, which XiiD route tools cannot cut. That is a finding for the architecture, not a
  tuning problem.

## Limits

- Attacker behaviour is a stochastic spread over the twin, not an adversary that adapts
  its goals; there is no stealth or deception model.
- A playbook runs once; there is no repeated escalation loop.
- Detection rates are placeholders. Real ones should come from the SOC's historical
  time-to-detect.
- Flow-hours count from containment until the end of the campaign; restoration time is not
  modelled.
