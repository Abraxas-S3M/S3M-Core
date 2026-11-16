# Capability 08 - Predictive Exposure Radar

**Status:** implemented and tested in the synthetic range. The intelligence inputs (CVSS,
EPSS, KEV) are synthetic, and the patch-ordering benefit is measured on simulated futures
that assume EPSS is calibrated. Code: `src/cortex/radar/exposure_radar.py`.

## What it does

The radar ranks weaknesses by what they do to the mission, not by their score in isolation,
and re-ranks when intelligence or topology changes.

| Piece | Method |
|---|---|
| Mission exposure | `M = Σ_a w_a · max_foothold P(path → a)` on the CyberTwin over protected assets (equal weights by default). |
| Forecast | EPSS is a 30-day probability, so the horizon value is `EPSS_T = 1 − (1 − EPSS)^(T/30)` (constant hazard). |
| Path importance | Counterfactual: how much `M` falls if this finding alone is fixed, with findings projected to the horizon. |
| Patch ordering | Sequential counterfactual greedy: fix the finding whose removal most reduces projected `M` per unit cost, then re-score, because closing one of two parallel paths changes the other's importance. When every single fix scores zero (redundant paths), it looks ahead at pairs. |
| Intelligence ingest | `epss_update`, `kev_added`, `new_finding`, `finding_fixed`, `route_change` → incremental re-score. An alert fires only if a finding enters the top N or its mission impact rises ≥ 0.05. |

## Measured (tests/cortex/test_exposure_radar.py, 8 tests)

**Ranking (enterprise_200).** The top finding is the ERP database auth bypass (CVSS 8.8,
CVSS rank 4). The CVSS 9.8 KEV gateway flaw (CVSS rank 1) scores zero. It only leads to
corporate users, whom the mission already models as compromised, so its rank depends on
that foothold assumption.

**Alerts:**

| Event | Alerts |
|---|---|
| KEV listing, then EPSS 0.97, on the print-server flaw (no onward routes) | none, in both cases |
| EPSS of the DC LDAP flaw 0.15 → 0.90 | DC LDAP **and** the CI pipeline flaw (CI → DC chain), both from importance 0 into the top 5 |
| New SMB flaw on the backup server | the new flaw **and** the file-server SMB flaw (file → backup chain) |
| Users' route to the ERP DB expired | ERP-DB finding importance falls |

**Greedy vs exhaustive, best first 2 and 4 fixes** (enterprise plus 4 random finding sets):
exactly optimal in 9 of 10 cases; the worst gap is 5.9% (enterprise, k = 2).

**Patch ordering over simulated futures:** 13 weeks, 2 fixes per week, 120–200 futures per
set. Each finding is weaponised at an exponential time implied by its EPSS; KEV means
already weaponised.

| Finding set | Radar, mission exposure-days | Best of CVSS / EPSS / KEV-then-CVSS | Reduction |
|---|---|---|---|
| enterprise_200 | 36.3 | 81.1 (EPSS) | 55% |
| 10 random sets | - | - | 0–59%, median ≈ 33% |

The radar is never worse than the best baseline on any set tested.

## Limits

- The value of the forecast depends entirely on EPSS calibration, and constant hazard is a
  simplification.
- Mission exposure inherits the twin's heuristic edge probabilities (see the CyberTwin doc);
  importance is relative, not an absolute breach probability.
- No external intelligence feed is connected. The ingest API takes events; wiring it to
  NVD, EPSS and KEV feeds is a deployment task and needs approved data egress.
- Patch cost defaults to 1 per finding; real maintenance windows should come from
  MissionGuardian.
