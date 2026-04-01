# GreyNoise Provider Runbook

## Purpose
GreyNoise classifies Internet background noise versus potentially targeted activity.

## API Access
- Base URL: `https://api.greynoise.io`
- Community endpoint: `/v3/community/{ip}`
- Header auth: `key`

## Tactical Use
- False-positive reducer for SOC analysts.
- `noise=true` or `riot=true` usually means de-prioritize.
- `noise=false` and `riot=false` is high-value and should be escalated.

## Air-gapped Notes
- Use curated fixture snapshots for standard scanner/riot/targeted scenarios.

## Smoke Test
```bash
pytest -q packages/providers/cyber-greynoise/tests/test_greynoise_adapter.py
```
