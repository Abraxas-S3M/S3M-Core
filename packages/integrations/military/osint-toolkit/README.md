# osint_toolkit Integration

## Purpose

This adapter wraps the `osint_toolkit` repository for S3M military and cyber
threat intelligence workflows.

Military/tactical context: it enables offline OSINT fusion rehearsal so threat
engineering teams can prepare detection priorities before live collection runs.

## Adapter Class

- `OsintToolkitAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.osint-toolkit`

## Operational Modes

- **Airgapped mode**: returns fixture data from `fixtures/sample_response.json`
- **Online mode**: validates local binary/path readiness and reports adapter
  status for mission orchestration

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
