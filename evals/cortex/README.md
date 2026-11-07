# Cortex evaluation suites (S1 range)

Versioned, offline-safe evaluation assets that gate Cortex releases.

## Suites

| Suite | Purpose |
| --- | --- |
| `defensive_tasks` | Triage accuracy, IOC extraction F1, attack-path NDCG on labelled synthetic cases |
| `injection` | 200+ text-pattern probes across logs, filenames, alerts, tool output, and retrieved docs |
| `false_containment` | Protected mission services must never be disrupted |
| `rollback` | Forced divergence/drift cases must restore state |
| `refusal` | Offensive cyber requests refused by every council role |
| `rug_pull_and_supply_chain` | Unsigned models and tampered manifests refused |

Hard thresholds live in `thresholds.yaml` and are enforced by `s3m_core.evaluation.cortex.CortexReleaseGate` together with `RegressionTracker`.

## Commands

```bash
# CI / deterministic (mocked engines)
PYTHONPATH=. python scripts/evaluation/run_cortex_evals.py --mode deterministic --model-version cortex-ci

# Nightly live range (archives JSON under artifacts/cortex_nightly)
PYTHONPATH=. python scripts/evaluation/run_cortex_evals.py --mode live --archive-dir artifacts/cortex_nightly
```

Red-team material is synthetic and defensive only (no working exploits, malware, or real credentials).
