"""
Canonical vault key templates for B2-backed artifact storage.

Tactical context:
    Stable key conventions guarantee that operators, training pipelines, and
    edge runtimes all reference the same mission artifact coordinates.
"""

VAULT_PATHS = {
    "base_weights": "base-weights/{engine_id}/",
    "quantized": "quantized/{engine_id}/",
    "datasets": "datasets/{track}/",
    "adapters": "adapters/{engine_id}/{track}/",
    "checkpoints_hetzner": "checkpoints/hetzner/{track}/",
    "checkpoints_runpod": "checkpoints/runpod/{engine_id}/",
    "eval_results": "eval-results/{engine_id}/{track}/",
    "grok_verdicts_pending": "grok-verdicts/pending/",
    "grok_verdicts_approved": "grok-verdicts/approved/",
    "grok_verdicts_rejected": "grok-verdicts/rejected/",
    "gui_snapshots": "gui-snapshots/",
    "scenario_packs": "datasets/{track}/scenarios/",
}
