# Project Le Chonk: staged replacement of S3M Mistral planning engine

Status: **INTEGRATION DESIGN ONLY — NO ROUTING OR INFERENCE ENABLED**
Date: 2026-11-07
Scope: S3M-Core quad-engine, Cortex, model admission, inference adapters. Keep four logical quad-engine roles.

## 1. Source-of-truth inventory

Original checkpoints in private R2 quarantine:
- `s3://s3m-vault/mistral-le-chonk/01-quarantine-original/fp8/`
  - upstream: `mistralai/Mistral-Large-4-1T-A52B`
  - source revision recorded by acquisition preflight: `af2627869af601441d6cdf75a1272469ddc3d059`
  - acquisition log reported 69 objects
- `s3://s3m-vault/mistral-le-chonk/01-quarantine-original/nvfp4/`
  - upstream: `mistralai/Mistral-Large-4-1T-A52B-NVFP4`
  - source revision recorded by acquisition preflight: `bb6d00fe249b0e876f0cffc6b85014be02de3e68`
  - acquisition log reported 44 objects
- `s3://s3m-vault/mistral-le-chonk/00-manifests/`

Acquisition script logs `ALL DONE`, but final independent inventory/object-size/hash and license-review signoff are **pending**. Do not execute files directly from R2 quarantine or auto-download them on server boot. Immutable original quarantine remains untouched. Verify original filenames, expected byte counts, upstream LFS digest where available, R2 object metadata, and separately read-back hash of sampled objects; full byte-for-byte read-back for production acceptance.

## 2. Current code gaps established from main branch

- `configs/engines.yaml` binds `quad_engine_map.planning_engine: mistral`, and `engines.mistral` describes legacy Mixtral 8x7B / one GGUF file.
- `src/llm_core/engine_registry.py` hardcodes `EngineID.MISTRAL = "mistral-7b"` and legacy Mixtral inference statistics.
- `src/quad_engine/model_registry.py` looks for **one bare model filename** and can mark an engine `live_local` just because a file exists and `S3M_ENABLE_LOCAL_LLM` is true.
- `src/quad_engine/local_llm.py` launches a **new llama.cpp process per request** with a 45s default timeout and single GGUF path. This cannot run a multi-file 1T model production service.
- `src/llm_core/backends/vllm_backend.py` already has private-endpoint policy, mTLS, model identity, health and attestation features. Prefer an adapter leveraging this instead of re-inventing remote execution.
- `src/cortex/model_admission.py` admission currently accepts format labels `safetensors` and `gguf` but does **single-file** `pinned_sha256` verification. Extend to multi-shard signed inventory and model revision checks. Do not circumvent admission.
- `src/quad_engine/models.py` status vocabulary is `live_local|placeholder|unavailable` and cannot faithfully express `registered|quarantined|audited|gpu_ready|cpu_ready|degraded`.
- `configs/model_manifests/mistral_7b.yaml` legacy numbers and files do not describe Le Chonk.
- `src/edge_runtime/model_planner.py` and training/export scripts hardcode legacy single-GGUF assumptions. Audit all references; do not mutate training/export or start training as part of integration.

## 3. Target configuration and compatibility

Introduce a new physical backing-model key `mistral_large_4` while keeping the **four** logical quad-engine IDs unchanged. Preserve the old `mistral` entry for **controlled rollback** until acceptance. After gating, switch `quad_engine_map.planning_engine` to `mistral_large_4`; not before.

Recommended model identity:
- model family: Mistral Large 4 / Le Chonk
- source: the two pinned Hugging Face revisions above; verify manifest model card and tokenizer details
- `fp8`: reference GPU evaluation checkpoint; multiple safetensors
- `nvfp4`: Blackwell-targeted optimized GPU candidate, **not** a universal CPU quantization
- `cpu_gguf`: **NOT ACQUIRED / NOT VERIFIED**; only register after officially or reproducibly converting a supported compatible GGUF, proving architecture and tokenizer correctness
- never label a truncated, pruned, distilled, or other student model as the full 1T model; use distinct identity `lechonk_student` and explicitly report lineage and loss of equivalence.

Service topology:
`COP/World Intelligence/approved input -> S3M-Core orchestrator -> planning_engine -> model admission + scheduler -> private LeChonk inference endpoint -> structured result/audit -> S3M-GUI`.
No GUI-to-R2, no direct Internet inference, no plaintext secrets. GPU workloads run on a dedicated approved multi-GPU inference node, not Hetzner CPU. Hetzner keeps the control plane; optional RunPod experiments only by explicit authorization. Strict private-network routing, TLS/mTLS, health/attestation, identities, RBAC and access logs. No tool execution by the model.

## 4. Engineering implementation sequence

1. **Admission and artifact package.** Add `configs/model_manifests/mistral_large_4.yaml` as *quarantined / not routable*. Manifest fields include: exact source revision, per-shard size+SHA256, signed manifest digest, tokenizer/config/chat-template hashes, intended precision, license text+approval, safety scan verdict, evaluation verdict, signer, hardware profile and runtime compatibility. Multi-shard verifier must fail closed on absent hash, unexpected files, size mismatch, signature mismatch and unknown model code. Production signing key must be supplied via secure vault, **never** default HMAC test key.
2. **Backend boundary.** Add a persistent OpenAI-compatible service client for the planning role. Reuse `VllmBackend` private network/attestation behavior, but validate actual Mistral Large 4 architecture support against pinned vLLM build and chosen hardware. No claim that a generic vLLM version will run model until a real smoke test passes. Support async jobs, bounded concurrency, context/token ceilings, idempotency, timeouts, circuit breaker, cancellation and sanitized error feedback.
3. **Scheduling.** Distinguish `fp8_gpu`, `nvfp4_blackwell_gpu`, `cpu_gguf_experimental`, `fallback_small_model`. Profile auto-selection must check actual hardware, free RAM/VRAM, pinned runtime build, successful model-load self test and approval. Never silently select CPU to run 1T when no supported compact artifact exists.
4. **Quad status model.** Preserve existing public engine IDs; add factual backend readiness fields without breaking legacy dashboard consumers. Report `registered`, `quarantined`, `admitted`, `weights_present`, `backend_healthy`, `model_loaded`, `last_live_response_at`, `precision`, `revision`, `runtime`, `device`, and `fallback_reason`. **Do not** classify a file-exists check as live inference.
5. **CPU operation.** The full 1T weights cannot run usefully on ordinary Hetzner CPU or Jetson. Only evaluate a separately-created compatible quantization on a high-memory CPU node, with measured throughput. For smaller CPU/edge deployments, distill supported capabilities into a distinctly named student; continue to use legacy small planning model as temporary fallback.
6. **Evaluations.** Verify load, tokenizer, instruct template, long-context **at progressively tested lengths**, bilingual EN/AR, structured JSON, domain outputs, hallucinations, prompt injection, tool-denial, confidentiality, latency p50/p95, throughput, batch, concurrent calls, VRAM, recovery, outage fallback, and audit trails. Ensure sample outputs are marked human-review-required; no autonomous action.
7. **Rollout.** Feature flag `S3M_LECHONK_ENABLED=false` by default. Run unit tests and isolated sandbox E2E. Canary to a nonproduction route with simulated data, compare against legacy planning engine, obtain approval and promote; keep rollback switch, old artifacts and immutable quarantine for at least one release cycle.

## 5. Acceptance gates

**A (inventory):** 69/69 FP8 and 44/44 NVFP4 objects independently verified against upstream pinned revision and per-file hashes; signed manifest generated; license cleared.

**B (security):** zero unreviewed loaders/network callbacks; static scan, SBOM, dependency pinning and isolated behavior tests pass; unsigned admission fails.

**C (GPU):** complete model loads on selected approved GPU topology; actual inference passes fixed test vectors; latency/VRAM/context and failure envelopes recorded.

**D (CPU):** actual CPU-compatible artifact exists and is validated on target hardware, otherwise status remains **unsupported / experimental**. Smaller student model must be identified separately.

**E (orchestrator):** planning requests reach Le Chonk in canary, return schema-valid structured outputs and audit/model provenance; other three engine roles unchanged. Offline/unavailable endpoint is explicitly shown as fallback, not disguised as live.

**F (promotion):** human signoff; rollback confirmed; production flag enabled only after all relevant mandatory gates pass.

## 6. Hard limits for this branch

No training, GPU provisioning, docker/server restarts, changes to live S3M-GUI, direct R2 downloads, secrets handling, or production routing. This document is an engineering handoff and does not claim any model has been executed or deployed.
