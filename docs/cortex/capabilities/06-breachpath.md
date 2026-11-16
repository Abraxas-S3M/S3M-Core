# Capability 06 - BreachPath Eliminator (exact optimiser)

**Status:** implemented and tested in the synthetic range. No live XiiD data. Novelty
requires a prior-art search; min-cost attack-graph hardening is an established field.

## Question it answers

*What is the cheapest set of reversible route changes that brings every protected asset's
worst attack-path probability under a target, without breaking a required flow or
exceeding mission limits?* And when the target is unreachable: *why not?*

## Method

- Constraint programming (OR-Tools CP-SAT), with log-probabilities scaled to integers.
- Decision variables per actionable route: narrow (only if a narrower prefix exists) or
  expire (only if no required flow depends on it and mission policy allows).
- A path is satisfied if any edge on it is expired, or if its probability after narrowing
  is below the asset's threshold.
- **Lazy path generation:** solve over the paths known so far, simulate the plan on the
  twin, add each pair's new worst path, repeat. Stopping with nothing new proves optimality
  over the full exponential path set.
- **Two phases:** first minimise unavoidable excess exposure, then minimise cost at that
  residual. The cost is change cost + irreversibility penalty + log-scaled disruption of observed sessions.
- **Residual explanations:** each pair left above target lists its blocking edges
  (required flows by id, identity edges, non-actionable routes).
- Mission constraints (`PlanConstraints`): forbidden actions per route, expiry policy,
  maximum changes, maximum irreversible changes, maximum disrupted sessions. MissionGuardian produces these.

Code: `src/cortex/breachpath/optimizer.py`, `analysis.py`. The architect adds it as
**OPT-D**; `DefenseCycle(exposure_target=...)` recommends the cheapest option reaching the
exposure OPT-D proved achievable.

## Measured results (range)

**Enterprise_200, target 0.30:** OPT-D needs 2 changes (expire `rt-users-erpdb`, narrow
`rt-users-jump-rdp`). The greedy recommendation (OPT-B) used 4 changes for the same ERP-database
exposure (0.496 → 0.269). On the matched objective, the exact plan scores lower than greedy.
Trade-off: OPT-B reaches a lower *aggregate* risk (0.822 vs 0.885) by closing paths already below target.

**Floor:** the domain controller cannot go below 0.317, and the databases and backup server
below 0.269, with route policy alone. The blocking edge is the required Kerberos flow
`rt-users-dc` (F-AUTH) plus domain-control identity edges. Identity hardening is the next lever.

**Exact vs greedy, same objective, 15 synthetic networks (each asset's exposure cut 75%):**

| Network size (edges) | Runs | Exact never worse | Exact strictly better | Saving where better | Max solve time |
|---|---|---|---|---|---|
| ~200 | 3 | 3 | 3 | 33-44% | < 0.1 s |
| ~550-600 | 3 | 3 | 2 | 29-52% | 0.1 s |
| ~1,800-1,900 | 3 | 3 | 1 | 64% | 0.2 s |
| ~5,600 | 3 | 3 | 3 | 16-58% | 0.6 s |
| ~18,000 | 3 | 3 | 1 | 61% | 2.3 s |

All solutions were proven optimal. Synthetic networks have uncalibrated, very low absolute
probabilities; only the relative comparison is meaningful.

**Correctness:** for 7 small networks, the solver's plan equals the exhaustive-search minimum
(`tests/cortex/test_breachpath.py`). 5 more were too large to enumerate and are skipped, not counted.

## Greedy planner fix (16 Nov)

`plan_mrc` used to refuse an expiry that removed all remaining risk (`reachability.py`,
`_pick_best_candidate`), so it could not close a lone attack path. That rule is removed;
required flows remain protected by the separate flow check. Regression test:
`test_greedy_can_close_a_lone_attack_path`, which fails on the old code and passes on the new.
The benchmark table above was measured *before* this fix, so greedy's numbers there are a lower bound.

## Limits

- Probabilities come from the twin's heuristic model until calibration (Wave 1, CyberTwin) lands.
- Narrowing is modelled as a fixed ×0.08 factor; real effect depends on the narrowed prefix.
- Core and regional release images install `ortools` via `requirements-cortex-planning.txt`.
  Edge images do not, as they do not run the planner.
