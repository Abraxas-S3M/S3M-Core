# AbuseIPDB Provider Runbook

## Purpose
AbuseIPDB provides rapid IP abuse confidence for triaging network-origin alerts.

## API Access
- Base URL: `https://api.abuseipdb.com/api/v2`
- Header auth: `Key`
- Free limits: ~1000 checks/day.

## Tactical Use
- Fast filter for brute-force and scanner IPs before deeper analyst escalation.
- Category tags support SOC playbook routing (SSH brute-force, port scan, DDoS).

## Air-gapped Notes
- Maintain periodic blacklist snapshot JSON for disconnected operations.

## Smoke Test
```bash
pytest -q packages/providers/cyber-abuseipdb/tests/test_abuseipdb_adapter.py
```
