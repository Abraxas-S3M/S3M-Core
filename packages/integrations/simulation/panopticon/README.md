# panopticon Integration

## Purpose

This adapter wraps the `panopticon` repository for S3M military simulation workflows.

Military/tactical context: it enables deterministic mission-tick outputs so staff planners can evaluate RL-guided tactical options without reliance on external connectivity.

## Adapter Class

- `PanopticonAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.simulation.panopticon`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path and local Python module availability

## Manifest

`get_manifest()` loads integration metadata from `manifest.yaml`.
