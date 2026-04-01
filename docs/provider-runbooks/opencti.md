# OpenCTI Provider Runbook

## Purpose
OpenCTI provides relationship-rich CTI context (actors, campaigns, malware, kill-chain) for mission-focused analysis.

## Setup
- Default URL: `http://localhost:8080`
- GraphQL endpoint: `/graphql`
- Set `S3M_OPENCTI_TOKEN` from user settings.

## Tactical Use
- Correlates IOC with threat actor and campaign context for command-level situational awareness.
- Complements MISP by adding graph relationships and STIX-native structures.

## Air-gapped Notes
- Export GraphQL query snapshots and store as fixture JSON.
- Execute provider tests only in `airgapped` mode when disconnected.

## Smoke Test
```bash
pytest -q packages/providers/cyber-opencti/tests/test_opencti_adapter.py
```
