# Recorded Future Provider Runbook

## Access
- API token via RF contract account.
- Environment variable:
  - `S3M_RECORDED_FUTURE_API_KEY`

## Intelligence Scope
- IP/domain/hash/CVE intelligence with risk scoring (0-99).
- Threat actor intelligence and triggered alerts.
- Dark web and predictive signal aggregation.

## Risk Scoring in S3M
- RF risk score maps directly to `reputation_score`.
- Severity mapping:
  - `>=80` critical
  - `>=60` high
  - `>=30` medium
  - `<30` low

## Tactical Usage
- Prioritize SOC response using high-confidence predictive indicators.
- Enrich IOC triage with risk-rule context and MITRE links.

## Air-Gapped Operations
- Keep approved intelligence snapshot fixtures.
- Replay enrichment and severity mapping logic offline.

## Smoke Test
```bash
python3 -m pytest packages/providers/cyber-recordedfuture/tests/ -v
```
