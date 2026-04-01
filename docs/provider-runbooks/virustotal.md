# VirusTotal Provider Runbook

## Purpose
VirusTotal delivers multi-engine reputation for IP/domain/hash/url observables.

## API Access
- Base URL: `https://www.virustotal.com/api/v3`
- Header auth: `x-apikey`
- Free-tier constraints: 4 req/min and 500/day.

## Tactical Use
- High-confidence malicious verdicts prioritize immediate containment in SOC workflows.
- Supports IOC confidence scoring during active incident response.

## Air-gapped Notes
- Use fixture snapshots for deterministic tests in disconnected environments.

## Smoke Test
```bash
pytest -q packages/providers/cyber-virustotal/tests/test_virustotal_adapter.py
```
