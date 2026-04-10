# wargames Integration

## Purpose

This adapter wraps the `wargames` repository for S3M training and simulation workflows.

Military/tactical context: command staffs can rehearse card-based engagements and evaluate expected loss/expenditure distributions while disconnected from external networks.

## Adapter Class

- `WargamesAdapter` in `adapter.py`
- Inherits from `packages.integrations.base.IntegrationAdapter`
- Logger namespace: `s3m.integrations.training_sim.wargames`

## Operational Modes

- **Airgapped mode**: returns deterministic fixture output from `fixtures/sample_response.json`
- **Online mode**: validates local binary/path availability and reports readiness

## Manifest

`get_manifest()` reads metadata from `manifest.yaml`.
