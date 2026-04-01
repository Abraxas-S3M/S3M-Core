# Langfuse Provider Runbook

## Purpose
Langfuse provides LLM observability and quality scoring for S3M Quad-LLM flows (Phi-3, Grok, Mistral, ALLaM).

## Setup
- Self-hosted default: `http://localhost:3000`
- Required:
  - `S3M_LANGFUSE_PUBLIC_KEY`
  - `S3M_LANGFUSE_SECRET_KEY`
- Optional:
  - `S3M_LANGFUSE_HOST`

## Tactical Context
- Full-trace telemetry supports mission after-action review and latency bottleneck triage in contested comms environments.
- Category tags align with operational functions (threat assessment, mission planning, command processing, etc.).

## S3M Categories
- threat_assessment
- mission_planning
- arabic_nlp
- tactical_decision
- adversary_reasoning
- maintenance_report
- intel_briefing
- command_processing
- risk_analysis

## Key Operations
- `get_traces(category=..., limit=...)`
- `get_daily_metrics(days=...)`
- `get_model_performance()`
- `get_category_breakdown()`
- `log_score(trace_id, name, value, comment)`
- `get_cost_summary(days=...)`
- `get_llm_health()`

## Air-gapped Notes
- Langfuse can run fully local in disconnected sites.
- Use local fixtures/tests to validate adapter behavior without outbound calls.

## Smoke Test
```bash
pytest -q packages/providers/ml-langfuse/tests/test_langfuse_adapter.py
```
