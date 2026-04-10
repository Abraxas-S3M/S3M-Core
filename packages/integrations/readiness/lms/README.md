# lms Integration

## Purpose

This adapter wraps the Frappe LMS repository for S3M training and certification readiness workflows.

Military/tactical context: it supports sovereign force preparation by tracking mission-critical course and certification compliance even in disconnected theaters.

## Adapter Class

- `LmsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.lms`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local LMS/Frappe dependency presence and reports orchestrator-ready status

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
