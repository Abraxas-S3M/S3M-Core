# pycmo Integration

## Purpose

This adapter wraps the `pycmo` repository for S3M simulation workflows.

Military/tactical context: it standardizes deterministic scenario-step outputs so mission planners can rehearse reinforcement-learning policies in sovereign, airgapped command environments.

## Adapter Class

- `PycmoAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.simulation.pycmo`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture data from `fixtures/sample_response.json`
- **Online mode**: validates configured binary/path and local Python module availability

## Manifest

`get_manifest()` loads integration metadata from `manifest.yaml`.
