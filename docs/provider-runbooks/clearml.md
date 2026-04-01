# ClearML Provider Runbook

## Purpose
ClearML provides pipeline orchestration, experiment metadata, model registry, and dataset version tracking for automated S3M retraining workflows.

## API Access
- Base URL: `https://api.clear.ml` or self-hosted `http://localhost:8008`
- Auth: access key + secret key
- S3M env vars:
  - `S3M_CLEARML_API_ACCESS_KEY`
  - `S3M_CLEARML_API_SECRET_KEY`
  - `S3M_CLEARML_API_HOST` (optional override)

## S3M Pipeline Templates
- `sar_retrain`: SAR detection retraining when new Label Studio annotations arrive.
- `rul_retrain`: predictive maintenance model retraining from telemetry drift.
- `arabic_finetune`: Arabic NLP fine-tuning.
- `yolo_finetune`: YOLO detection fine-tuning for tactical imagery.

## Tactical Workflow
1. Trigger retraining pipeline after validated dataset update.
2. Track task lineage, model artifact versions, and dataset hashes.
3. Promote validated model version to Hugging Face/local model cache.

## Air-gapped Notes
- Supports offline task logging for disconnected deployments.
- Keep ClearML Server on the same secure enclave network as edge training assets.

## Smoke Test
```bash
pytest -q packages/providers/ml-clearml/tests/test_clearml_adapter.py
```
