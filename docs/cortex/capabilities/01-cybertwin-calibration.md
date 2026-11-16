# Capability 01 - CyberTwin calibration

**Status:** implemented and validated against a *synthetic* hidden ground truth. Real
calibration needs reviewed exercise, red-team or incident outcomes from the customer environment.

## Model (`src/cortex/calibration.py`)

| Element | Method |
|---|---|
| Belief per route | Beta distribution over P(traverse \| attempted) |
| Prior | The twin's finding-based heuristic. Its **strength is fitted from the data** (empirical Bayes): how far observed exercise rates scatter around the heuristic, net of binomial noise. A good heuristic earns strength around 15; a poor one around 1.4. |
| Evidence | Reviewed outcomes `(attempts, successes, when, source)` |
| Pooling | Routes with little data borrow from their service class (hierarchical Beta-Binomial, method of moments) |
| Decay | Each outcome's weight halves every 90 days, so stale evidence widens uncertainty back toward the prior |
| Pressure | Denied-attempt telemetry → a decayed attempt rate per route, reported separately. It never changes the success probability. |
| Outputs | A calibrated twin (posterior mean or a conservative quantile) and Monte Carlo exposure intervals per asset (p05 / p50 / p95) |

`DefenseCycle(calibration=store, calibration_quantile=0.9)` calibrates every twin it builds
(planning, verification, rollback) the same way, and adds intervals to the report.

## Validation against hidden synthetic truth

The truth is the heuristic × lognormal error. That is deliberately a different family from the
model, so the results include misspecification.

| Measure (20 seeds, 60% of routes exercised, 5-40 attempts) | Result |
|---|---|
| Mean absolute error on exercised routes | 0.112 heuristic → 0.055 posterior (spread 0.6) |
| 90% interval coverage, exercised routes | 0.83-0.85 |
| 90% interval coverage, unexercised routes | 0.79-0.86 |
| True asset exposure inside the p05-p95 interval | 0.86 |
| Stale evidence (1 year) | Effective attempts 13 → 0.8; interval width 0.34 → 0.53 |

Intervals are **moderately overconfident** (about 85% observed for 90% nominal). Treat a
90% interval as roughly 85% until real data allows recalibration.

**Planning on calibrated twins (BreachPath, target 0.15, 20 seeds):**

| Plan built on | Claims that hold in the true world | Changes per plan |
|---|---|---|
| Heuristic | 100% | 3.00 |
| Posterior mean | 96.7% | 2.25 |
| Posterior 90th percentile | 100% | 3.25 |

The heuristic also held in this synthetic world. The value shown is quantified uncertainty
and a principled conservative option, not uniformly better plans.

## Limits

- The evidence model assumes independent attempts per route; correlated campaigns overstate certainty.
- Monte Carlo samples edges independently; correlated vulnerabilities (same software on many hosts) would widen real intervals.
- Pressure telemetry is reported but not yet used by the planner (Predictive Exposure Radar, Wave 2).
