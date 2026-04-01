# MISP Provider Runbook

## Purpose
MISP feeds structured indicators and event context into S3M CTI enrichment for tactical SOC and threat-hunting workflows.

## Deployment (Self-hosted)
- Default endpoint: `http://localhost:8443`
- Typical setup uses internal TLS/self-signed certificates.
- Generate API key in MISP user profile and set `S3M_MISP_API_KEY`.

## Supported API Flows
- `POST /attributes/restSearch` for IOC pull
- `POST /events/restSearch` for campaign/event context
- `GET /galaxies` for actor/malware/tool knowledge

## Military/Tactical Relevance
- Feeds Phase 13 SOCManager for alert enrichment.
- Feeds Phase 5 ThreatManager IOC matching bridge.
- Supplies Phase 19 intelligence center with campaign context and MITRE references.

## Warninglist
Keep `enforceWarninglist=true` to reduce known false positives before analyst triage.

## Air-gapped Operations
- Export MISP JSON from connected enclave.
- Transfer via approved removable media to `packages/providers/cyber-misp/fixtures/`.
- Run provider in `airgapped` mode.

## Smoke Test
```bash
pytest -q packages/providers/cyber-misp/tests/test_misp_adapter.py
```
