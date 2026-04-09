# OMPL Integration

## Purpose

This adapter wraps the OMPL repository for S3M military autonomy path-planning workflows.

Military/tactical context: it enables deterministic rehearsal of UAV route generation (for example RRT*) so planners can validate safe paths in denied environments without external connectivity.

## Adapter Class

- `OmplAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.military.ompl`

## Operational Modes

- **Airgapped mode**: deterministic fixture replay from `fixtures/sample_response.json`
- **Online mode**: local binary/path availability checks with orchestrator-ready status output

## Manifest

Adapter metadata is defined in `manifest.yaml` and returned by `get_manifest()`.
