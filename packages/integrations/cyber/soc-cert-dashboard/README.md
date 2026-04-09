# soc-cert-dashboard Integration

## Purpose

This adapter wraps `soc-cert-dashboard` for S3M SOC-CERT workflows.

Military/tactical context: it supports unified cyber defense command cycles where SOC and CERT elements must synchronize threat analysis in airgapped environments.

## Adapter Class

- `SocCertDashboardAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.cyber.soc-cert-dashboard`

## Operational Modes

- **Airgapped mode**: deterministic response from `fixtures/sample_response.json`
- **Online mode**: local binary/path readiness validation and structured readiness output

## Manifest

Integration metadata is stored in `manifest.yaml` and returned by `get_manifest()`.
