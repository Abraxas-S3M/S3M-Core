# Headcount (bluewave-labs) Integration

## Purpose

This adapter wraps the bluewave-labs Headcount repository for S3M HR and readiness workflows.

Military/tactical context: it supports sovereign workforce planning by exposing personnel and time-off data needed for mission staffing decisions.

## Adapter Class

- `HeadcountbluewaveLabsAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.readiness.headcount-bluewave-labs`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local runtime dependency presence and reports orchestrator-ready status

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
