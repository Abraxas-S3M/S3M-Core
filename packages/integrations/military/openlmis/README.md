# OpenLMIS Integration

## Purpose

This adapter wraps the `openlmis-ref-distro` repository for S3M military
sustainment and distribution workflows.

Military/tactical context: it supports disconnected logistics rehearsal so
commanders can prioritize resupply under contested route constraints.

## Adapter Class

- `OpenlmisAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.openlmis`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: checks local stack binary/path readiness and reports adapter
  status to orchestrator pipelines

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
