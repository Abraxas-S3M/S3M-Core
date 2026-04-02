# S3M Unified Quad-Engine Runtime

## What Changed

The quad-engine system has been upgraded from an orchestration shell with
simulated outputs into a live synchronized runtime with:

1. **Live engine execution** — `EngineRuntimeAdapter` invokes real
   llama.cpp engines via EnginePool; never returns simulated text.
2. **Shared mission state** — `MissionState` is a versioned, thread-safe
   blackboard that all engines write into with provenance tagging.
3. **Structured outputs** — Every engine returns `StructuredEngineOutput`
   with typed threats, actions, evidence, and state updates.
4. **Conflict reconciliation** — `ReconciliationEngine` detects and
   resolves disagreements (threat classification, confidence, actions)
   using trust weights, domain specialization, ROE rules, and evidence depth.
5. **Unified runtime** — `UnifiedRuntime.execute_mission()` runs the
   complete 10-step pipeline from request to authoritative decision.

## Architecture

```
MissionRequest
    │
    ▼
UnifiedRuntime.execute_mission()
    │
    ├── 1. Ingest request
    ├── 2. Build MissionContext → MissionState
    ├── 3. Route engines (domain / consensus / explicit)
    ├── 4. EngineRuntimeAdapter.execute_engines() [LIVE]
    ├── 5. Collect StructuredEngineOutput per engine
    ├── 6. MissionState.ingest_engine_output() [provenance tagged]
    ├── 7. ReconciliationEngine.reconcile() [conflict resolution]
    ├── 8. Produce DecisionRecord [authoritative]
    ├── 9. Persist audit trail + version history
    └── 10. Return MissionResult
```

## Shared Memory

MissionState is a thread-safe blackboard containing:
- Threat entities (deduplicated, trust-weighted)
- Action candidates (ROE-filtered, ranked)
- Evidence items (with provenance)
- Conflict records (with resolution strategy)
- Version history (every mutation tracked)
- Engine contributions (who wrote what, when, with what confidence)

## Reconciliation

Conflicts are resolved by strategy:
- **HIGHER_CONFIDENCE_WINS**: default for most disagreements
- **DOMAIN_SPECIALIST_WINS**: for threat classification (Grok preferred)
- **WEIGHTED_MERGE**: for confidence disagreements (trust-weighted average)
- **ESCALATE_TO_HUMAN**: for offensive actions under restrictive ROE
- **ROE-aware**: defensive actions preferred under weapons_hold
