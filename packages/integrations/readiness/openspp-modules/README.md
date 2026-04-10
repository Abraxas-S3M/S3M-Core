# openspp-modules Integration

## Purpose

This adapter wraps the OpenSPP modules repository for S3M personnel and beneficiary readiness workflows.

Military/tactical context: it supports sovereign force-readiness planning by correlating personnel availability and support registries under disconnected operating conditions.

## Adapter Class

- `OpensppModulesAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.openspp-modules`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local OpenSPP/Odoo dependency presence and reports orchestrator-ready status

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
