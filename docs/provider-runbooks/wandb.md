# W&B Provider Runbook

## Purpose
Weights & Biases tracks model training runs, metrics, and artifacts for S3M.

## Authentication
- `S3M_WANDB_API_KEY` (required)
- `S3M_WANDB_BASE_URL` (optional for self-hosted W&B)
- `WANDB_MODE=offline` for air-gapped local logging

## S3M Projects
- `s3m-sar-detection`
- `s3m-threat-detection`
- `s3m-rul-prediction`
- `s3m-rl-autonomy`
- `s3m-arabic-nlp`
- `s3m-wargaming-adversary`

## Tactical Workflow
1. Start training with W&B logging enabled.
2. Track best run by mission metric (`mAP`, `f1`, or latency-bound score).
3. Export best artifact to edge packaging pipeline.

## Air-gapped Notes
- Use offline mode during disconnected operations.
- Sync logs only in approved secure enclaves.

## Smoke Test
```bash
pytest -q packages/providers/ml-wandb/tests/test_wandb_adapter.py
```
