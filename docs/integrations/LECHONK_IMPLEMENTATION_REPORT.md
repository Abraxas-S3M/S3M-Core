# Le Chonk quad-engine implementation report

**Date:** 2026-11-07  
**Branch:** `cursor/lechonk-quad-engine-integration`  
**Status:** Implementation-ready staging — **no production routing, no inference activation**

## Summary

This iteration adds a staged integration package under `src/integrations/lechonk/`, extends admission and quad-engine status reporting, registers `mistral_large_4` in `configs/engines.yaml`, and keeps `quad_engine_map.planning_engine` on legacy `mistral` for rollback. `S3M_LECHONK_ENABLED` remains off by default and `execution_enabled: false` in the manifest blocks routing even if the env var is set.

## Completed changes

| Area | Deliverable |
|------|-------------|
| Multi-shard inventory | `shard_inventory.py`, lab JSON fixtures under `configs/model_manifests/inventories/`, `ModelAdmissionGate.evaluate_shard_inventory` / `admitted_with_shards` |
| vLLM planning adapter | `planning_backend.py` wrapping `VllmBackend` with concurrency limits, circuit breaker, sanitized errors, provenance metadata |
| Orchestrator config | `engines.mistral_large_4` quarantined; legacy `mistral` preserved; planning map unchanged |
| Deployment profiles | `fp8_gpu`, `nvfp4_blackwell_gpu`, `cpu_gguf_experimental`, `fallback_small_model` in `deployment_profiles.py` + scheduler |
| Hardware / resilience | `hardware.py` probes, `circuit_breaker.py`, scheduler resource gates |
| Status reporting | `status.py`, `BackendReadiness` on `EngineRecord` / `OrchestratorStatus`, `/api/quad-engine/status` fields |
| CPU interfaces | `cpu_gguf` variant marked `unavailable`; scheduler never selects 1T CPU without verified artifact |
| Admission / audit | Shard requirement on evaluate; orchestrator audit `planning_backing`; human review unchanged |
| Tests | `tests/integrations/lechonk/*` covering shards, admission, routing, fallback, backend, status, audit |

## Explicitly not done (by policy)

- No R2/quarantine weight download or execution
- No GPU provisioning, Docker/Hetzner restarts, or production flag enablement
- No live Mistral Large 4 inference smoke test ( `inference_verified` stays false )
- Full 69/44 shard SHA-256 production inventory (gate A pending)
- `quad_engine_map.planning_engine` **not** switched to `mistral_large_4`

## Unsupported / pending features

- NVFP4 on non-Blackwell hardware (rejected by scheduler without Blackwell hint)
- CPU GGUF for full 1T model (documented unavailable)
- Production signed admission (HMAC test key only in dev; vault key required for promotion)
- vLLM architecture support unverified until operator sets smoke test and pinned build (`S3M_LECHONK_VLLM_BUILD`)

## Hardware requirements (actual)

| Profile | Requirement |
|---------|-------------|
| `fp8_gpu` | Multi-GPU node with private vLLM; staging threshold ~400GB host RAM in scheduler (conservative, not benchmarked) |
| `nvfp4_blackwell_gpu` | Blackwell-class GPU hint via `nvidia-smi`; NVFP4 weights in quarantine |
| `fallback_small_model` | Legacy Mixtral GGUF path on regional CPU/GPU edge |
| Control plane | Existing Hetzner CPU stack; Le Chonk inference on dedicated approved GPU endpoint only |

## Test execution

Run locally:

```bash
pytest tests/integrations/lechonk tests/cortex/test_model_admission.py tests/test_quad_engine.py tests/test_vllm_backend.py -q
```

**Agent run (2026-11-07):** `41 passed` in `tests/integrations/lechonk`, `tests/test_quad_engine.py`, `tests/test_vllm_backend.py` (cortex conftest skipped due to optional `mcp` dependency in full tree).

## Rollback

1. Keep `S3M_LECHONK_ENABLED` unset or `false`
2. `quad_engine_map.planning_engine: mistral` (unchanged)
3. Quarantined `mistral_large_4` engine remains non-routable via admission status
